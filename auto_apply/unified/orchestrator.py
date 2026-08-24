"""
Orquestador principal de aplicaciones (Job Radar pattern).

Estado machine: ANALYZE → NAVIGATE → AUTH → FILL → VALIDATE → REVIEW → SUBMIT

Características:
- Checkpointing en cada etapa
- Review gate: NUNCA submit sin aprobación humana
- Manejo de errores y reintentos
- Notificaciones push para intervención humana
- Sesión persistente de navegador
"""
import asyncio
import logging
from typing import Any, Dict, Optional
from playwright.async_api import Page
from .state import ApplicationState, ApplicationStatus
from .session import BrowserSessionManager, get_global_session
from .fillers import get_filler, FILLER_REGISTRY, FillResult
from .account import AccountManager
from .notifications import NotificationManager, get_notification_manager
from auto_apply import detect_ats
from job_data import job_folder_manager, application_data, JobFolderManager, ApplicationDataManager

logger = logging.getLogger(__name__)


class ApplicationOrchestrator:
    """
    Orquestador principal de auto-aplicación.
    
    Flujo:
    1. ANALYZE: Detecta ATS, analiza estructura del formulario
    2. NAVIGATE: Navega a URL, maneja landing pages, clicks "Apply"
    3. AUTH: Login, crear cuenta, verificación email si necesario
    4. FILL: Llena formulario con filler específico del ATS
    5. VALIDATE: Verifica campos, detecta errores, campos rotos
    6. REVIEW: Prepara datos para revisión humana (review gate)
    7. SUBMIT: Replay exacto de lo aprobado (cero nuevas llamadas LLM)
    """
    
    def __init__(
        self,
        job_data: dict,
        candidate_data: dict,
        session_manager: BrowserSessionManager = None,
        account_manager: AccountManager = None,
        notification_manager: NotificationManager = None,
        config: dict = None,
    ):
        self.job_data = job_data
        self.candidate_data = candidate_data
        self.config = config or {}
        
        # Detectar ATS
        self.ats_type = detect_ats(job_data.get("url", "")) or "unknown"
        
        # Job folder manager (Proficiently-inspired)
        self.job_folder_manager = job_folder_manager
        self.application_data = application_data
        
        # Create job folder structure
        self.job_app = self.job_folder_manager.create_job_folder(job_data)
        
        # Managers
        self.session_manager = session_manager
        self.account_manager = account_manager or AccountManager(session_manager, config)
        self.notification_manager = notification_manager or get_notification_manager(config)
        
        # Estado
        self.state = ApplicationState(
            job_id=job_data.get("id", 0),
            job_url=job_data.get("url", ""),
            ats_type=self.ats_type,
            job_data=job_data,
            candidate_data=candidate_data,
        )
        
        # Page reference (se asigna en run)
        self.page: Optional[Page] = None
        self.app_id: str = self.state.application_id
        
        # Filler
        self.filler = None
    
    async def run(self, semi_auto: bool = True, headless: bool = False) -> ApplicationState:
        """
        Ejecuta pipeline completo de aplicación.
        
        Args:
            semi_auto: Si True, espera aprobación humana antes de submit
            headless: Si True, browser headless (no recomendado para semi-auto)
        
        Returns: Estado final de la aplicación
        """
        logger.info(f"[{self.app_id}] Starting application for {self.job_data.get('title')} @ {self.job_data.get('company')}")
        
        try:
            # Obtener sesión de navegador
            if not self.session_manager:
                self.session_manager = await get_global_session(headless=headless)
            
            self.page = await self.session_manager.get_page(self.app_id)
            self.page.on("close", lambda: self._on_page_close())
            
            # Inicializar filler específico del ATS
            self.filler = get_filler(self.ats_type, self.page, self.job_data, self.candidate_data)
            
            # Ejecutar máquina de estados
            await self._run_state_machine(semi_auto)
            
        except Exception as e:
            logger.error(f"[{self.app_id}] Fatal error: {e}", exc_info=True)
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = str(e)
        
        finally:
            # Cleanup
            await self._cleanup()
        
        return self.state
    
    async def _run_state_machine(self, semi_auto: bool):
        """Ejecuta máquina de estados completa."""
        
        # 1. ANALYZE
        await self._step_analyze()
        if self.state.status == ApplicationStatus.FAILED:
            return
        
        # 2. NAVIGATE
        await self._step_navigate()
        if self.state.status == ApplicationStatus.FAILED:
            return
        
        # 3. AUTH
        await self._step_authenticate()
        if self.state.status == ApplicationStatus.FAILED:
            return
        
        # 4. FILL
        await self._step_fill()
        if self.state.status == ApplicationStatus.FAILED:
            return
        
        # 5. VALIDATE
        await self._step_validate()
        if self.state.status == ApplicationStatus.FAILED:
            return
        
        # 6. REVIEW (Review Gate - nunca submit sin aprobación)
        await self._step_review(semi_auto)
        if self.state.status in (ApplicationStatus.PARKED, ApplicationStatus.CAPTCHA_BLOCKED):
            return  # Esperando intervención humana
        
        if not self.state.human_approved:
            logger.info(f"[{self.app_id}] Human rejected or not approved")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = "Not approved by human"
            return
        
        # 7. SUBMIT (Replay exacto)
        await self._step_submit()
    
    async def _step_analyze(self):
        """ANALYZE: Detecta ATS y analiza estructura."""
        self.state.update_status(ApplicationStatus.ANALYZING, "analyze")
        logger.info(f"[{self.app_id}] ANALYZE: Detecting ATS structure")
        
        try:
            analysis = await self.filler.analyze()
            self.state.add_checkpoint("analyze", analysis)
            
            # Detectar ATS si no se sabía
            if self.ats_type == "unknown" and "ats" in analysis:
                self.ats_type = analysis["ats"]
                self.state.ats_type = self.ats_type
                # Re-inicializar filler correcto
                self.filler = get_filler(self.ats_type, self.page, self.job_data, self.candidate_data)
            
            logger.info(f"[{self.app_id}] ANALYZE complete: {analysis}")
        except Exception as e:
            logger.error(f"[{self.app_id}] ANALYZE failed: {e}")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = f"Analyze failed: {e}"
    
    async def _step_navigate(self):
        """NAVIGATE: Navega a URL, maneja landing pages."""
        self.state.update_status(ApplicationStatus.NAVIGATING, "navigate")
        logger.info(f"[{self.app_id}] NAVIGATE: Going to {self.state.job_url}")
        
        try:
            await self.page.goto(self.state.job_url, wait_until="domcontentloaded", timeout=60000)
            await self.page.wait_for_load_state("networkidle")
            self.state.page_url = self.page.url
            
            # Navegación específica del ATS
            nav_success = await self.filler.navigate()
            if not nav_success:
                raise Exception("Navigation failed - could not reach application form")
            
            self.state.add_checkpoint("navigate", {"url": self.page.url})
            logger.info(f"[{self.app_id}] NAVIGATE complete: {self.page.url}")
        except Exception as e:
            logger.error(f"[{self.app_id}] NAVIGATE failed: {e}")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = f"Navigate failed: {e}"
    
    async def _step_authenticate(self):
        """AUTH: Login, crear cuenta, verificación email."""
        self.state.update_status(ApplicationStatus.AUTHENTICATING, "authenticate")
        logger.info(f"[{self.app_id}] AUTH: Checking authentication")
        
        try:
            # Verificar si ATS requiere auth
            auth_required = not await self.filler.authenticate()
            
            if auth_required:
                # Usar AccountManager
                credentials = self.config.get("ats_credentials", {}).get(self.ats_type, {})
                auth_success = await self.account_manager.ensure_account(
                    self.ats_type, self.page, credentials
                )
                
                if not auth_success:
                    # Semi-auto: esperar intervención humana
                    self.state.update_status(ApplicationStatus.CAPTCHA_BLOCKED, "auth_waiting")
                    await self.notification_manager.notify_human_needed(
                        self.ats_type,
                        self.job_data.get("title", ""),
                        "Login or account creation required",
                        self.page.url,
                    )
                    
                    result = await self.session_manager.wait_for_human(
                        self.app_id,
                        f"Complete login/account creation for {self.ats_type}",
                        timeout=300
                    )
                    
                    if result["action"] != "continue":
                        raise Exception("Authentication cancelled by human")
            else:
                logger.info(f"[{self.app_id}] No authentication required")
            
            self.state.add_checkpoint("authenticate", {"auth_required": auth_required})
        except Exception as e:
            logger.error(f"[{self.app_id}] AUTH failed: {e}")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = f"Authentication failed: {e}"
    
    async def _step_fill(self):
        """FILL: Llena formulario con filler específico."""
        self.state.update_status(ApplicationStatus.FILLING, "fill")
        logger.info(f"[{self.app_id}] FILL: Filling application form")
        
        try:
            fill_result = await self.filler.fill()
            
            self.state.filled_fields = fill_result.filled_fields
            self.state.validation_errors = fill_result.validation_errors
            self.state.broken_fields = fill_result.broken_fields
            self.state.error_message = fill_result.error_message
            
            # Save form answers to application-data.md (Proficiently-inspired)
            for label, value in fill_result.filled_fields.items():
                application_data.save_answer(label, value, self.ats_type)
            
            self.state.add_checkpoint("fill", {
                "filled_count": len(fill_result.filled_fields),
                "errors": len(fill_result.validation_errors),
                "broken": len(fill_result.broken_fields),
            })
            
            logger.info(f"[{self.app_id}] FILL complete: {len(fill_result.filled_fields)} fields, "
                       f"{len(fill_result.validation_errors)} errors, "
                       f"{len(fill_result.broken_fields)} broken")
            
        except Exception as e:
            logger.error(f"[{self.app_id}] FILL failed: {e}")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = f"Fill failed: {e}"
    
    async def _step_validate(self):
        """VALIDATE: Verifica campos, detecta errores y campos rotos."""
        self.state.update_status(ApplicationStatus.VALIDATING, "validate")
        logger.info(f"[{self.app_id}] VALIDATE: Validating form")
        
        try:
            validation_result = await self.filler.validate()
            
            self.state.validation_errors = validation_result.validation_errors
            self.state.broken_fields = validation_result.broken_fields
            
            self.state.add_checkpoint("validate", {
                "errors": len(validation_result.validation_errors),
                "broken": len(validation_result.broken_fields),
            })
            
            # Si hay campos rotos, notificar
            if validation_result.broken_fields:
                await self.notification_manager.notify_broken_form(
                    self.ats_type,
                    self.job_data.get("title", ""),
                    validation_result.broken_fields,
                    self.page.url,
                )
            
            logger.info(f"[{self.app_id}] VALIDATE complete: {len(validation_result.validation_errors)} errors, "
                       f"{len(validation_result.broken_fields)} broken fields")
            
        except Exception as e:
            logger.error(f"[{self.app_id}] VALIDATE failed: {e}")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = f"Validate failed: {e}"
    
    async def _step_review(self, semi_auto: bool):
        """REVIEW: Review gate - prepara datos para aprobación humana."""
        self.state.update_status(ApplicationStatus.HUMAN_REVIEW, "review")
        logger.info(f"[{self.app_id}] REVIEW: Preparing for human review (semi_auto={semi_auto})")
        
        try:
            # Preparar datos de revisión
            fill_result = FillResult(
                success=len(self.state.validation_errors) == 0,
                filled_fields=self.state.filled_fields,
                validation_errors=self.state.validation_errors,
                broken_fields=self.state.broken_fields,
            )
            
            review_data = await self.filler.review_prepare(fill_result)
            self.state.review_data = review_data
            self.state.review_screenshot = review_data.get("screenshot")
            
            self.state.add_checkpoint("review", review_data)
            
            if semi_auto:
                # REVIEW GATE: Esperar aprobación humana
                logger.info(f"[{self.app_id}] Waiting for human approval...")
                
                # Notificar para revisión
                await self.notification_manager.notify_human_needed(
                    self.ats_type,
                    self.job_data.get("title", ""),
                    f"Review application before submit\nFilled: {len(self.state.filled_fields)} fields\nErrors: {len(self.state.validation_errors)}\nBroken: {len(self.state.broken_fields)}",
                    self.page.url,
                )
                
                # En semi-auto, el humano revisa en el browser abierto
                # wait_for_human monitorea submit manual
                result = await self.session_manager.wait_for_human(
                    self.app_id,
                    "Review application, fill broken fields, solve CAPTCHA, then click Submit",
                    timeout=600  # 10 minutos
                )
                
                if result["action"] == "continue":
                    # Verificar si el humano hizo submit y fue exitoso
                    if "url" in result and any(x in result["url"].lower() for x in ["/thanks", "/success", "/confirmation"]):
                        self.state.human_approved = True
                        self.state.success = True
                        self.state.update_status(ApplicationStatus.SUBMITTED)
                        return
                    
                    self.state.human_approved = True
                    self.state.human_edits = result.get("data", {})
                    logger.info(f"[{self.app_id}] Human approved, proceeding to submit")
                else:
                    logger.info(f"[{self.app_id}] Human cancelled or timeout")
                    self.state.update_status(ApplicationStatus.PARKED)
                    self.state.error_message = "Cancelled by human or timeout"
            else:
                # Auto mode: solo aprobar si no hay errores ni campos rotos
                if len(self.state.validation_errors) == 0 and len(self.state.broken_fields) == 0:
                    self.state.human_approved = True
                    logger.info(f"[{self.app_id}] Auto-approved (no errors/broken fields)")
                else:
                    self.state.update_status(ApplicationStatus.PARKED)
                    self.state.error_message = "Auto mode: errors or broken fields require human review"
            
        except Exception as e:
            logger.error(f"[{self.app_id}] REVIEW failed: {e}")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = f"Review failed: {e}"
    
    async def _step_submit(self):
        """SUBMIT: Envía aplicación (con verificación Zoho si aplica)."""
        self.state.update_status(ApplicationStatus.SUBMITTING, "submit")
        logger.info(f"[{self.app_id}] SUBMIT: Submitting application")
        
        try:
            # Preferir submit_application del filler (incluye flujo Zoho post-submit)
            if hasattr(self.filler, "submit_application"):
                submit_result = await self.filler.submit_application()
            else:
                submit_result = await self.filler.submit_replay(self.state.human_edits)
            
            self.state.success = submit_result.success
            self.state.submit_response = submit_result.error_message or "Submitted"
            
            if submit_result.success:
                self.state.update_status(ApplicationStatus.SUBMITTED)
                logger.info(f"[{self.app_id}] SUBMIT success!")
                
                # Save job folder with all files (Proficiently-inspired)
                self.job_folder_manager.save_resume(self.job_app, self.candidate_data.get("resume_content", ""))
                self.job_folder_manager.save_cover_letter(self.job_app, self.candidate_data.get("cover_letter_content", ""))
                self.job_folder_manager.log_application(self.job_app, self.state.to_dict())
                
                logger.info(f"[{self.app_id}] SUBMIT success!")
                
                # Notificar éxito
                await self.notification_manager.notify_success(
                    self.ats_type,
                    self.job_data.get("title", ""),
                    self.job_data.get("company", ""),
                    self.page.url,
                )
            else:
                self.state.update_status(ApplicationStatus.FAILED)
                self.state.error_message = submit_result.error_message
                logger.error(f"[{self.app_id}] SUBMIT failed: {submit_result.error_message}")
                
                # Log failed application
                self.job_folder_manager.log_application(self.job_app, self.state.to_dict())
                
                await self.notification_manager.notify_failure(
                    self.ats_type,
                    self.job_data.get("title", ""),
                    submit_result.error_message,
                    self.page.url,
                )
            
            self.state.add_checkpoint("submit", {"success": submit_result.success})
            
        except Exception as e:
            logger.error(f"[{self.app_id}] SUBMIT failed: {e}")
            self.state.update_status(ApplicationStatus.FAILED)
            self.state.error_message = f"Submit failed: {e}"
    
    async def _cleanup(self):
        """Limpieza final."""
        try:
            await self.session_manager.save_storage_state()
            await self.session_manager.close_page(self.app_id)
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
    def _on_page_close(self):
        """Callback cuando se cierra la página."""
        logger.info(f"[{self.app_id}] Page closed externally")


# Función de conveniencia para uso directo
async def apply_to_job(
    job_data: dict,
    candidate_data: dict,
    semi_auto: bool = True,
    headless: bool = False,
    config: dict = None,
) -> ApplicationState:
    """
    Función principal para aplicar a un job.
    
    Args:
        job_data: Dict con datos del job (id, title, company, url, etc.)
        candidate_data: Dict con datos del candidato
        semi_auto: Si True, espera aprobación humana
        headless: Si True, browser headless
        config: Configuración adicional (credenciales, notificaciones, etc.)
    
    Returns: ApplicationState con resultado completo
    """
    orchestrator = ApplicationOrchestrator(
        job_data=job_data,
        candidate_data=candidate_data,
        config=config or {},
    )
    return await orchestrator.run(semi_auto=semi_auto, headless=headless)