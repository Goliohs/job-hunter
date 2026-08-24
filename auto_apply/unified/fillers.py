"""
Registro de fillers específicos por ATS (Job Radar pattern).

Cada ATS tiene su propio filler con lógica específica.
NO hay filler genérico - cada uno conoce su estructura.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from playwright.async_api import Page
import logging

logger = logging.getLogger(__name__)


@dataclass
class FillResult:
    """Resultado de llenado de formulario."""
    success: bool
    filled_fields: dict = None
    validation_errors: list = None
    broken_fields: list = None
    error_message: str = ""
    screenshot: str = ""
    
    def __post_init__(self):
        if self.filled_fields is None:
            self.filled_fields = {}
        if self.validation_errors is None:
            self.validation_errors = []
        if self.broken_fields is None:
            self.broken_fields = []


class ATSBaseFiller(ABC):
    """Base para fillers específicos de ATS."""
    
    def __init__(self, page: Page, job_data: dict, candidate_data: dict):
        self.page = page
        self.job_data = job_data
        self.candidate_data = candidate_data
        self.filled = {}
        self.errors = []
        self.broken = []
    
    @abstractmethod
    async def analyze(self) -> dict:
        """
        ANALYZE: Detecta estructura del formulario.
        Returns: dict con info de campos, tipo de ATS, etc.
        """
        pass
    
    @abstractmethod
    async def navigate(self) -> bool:
        """
        NAVIGATE: Navega al formulario, maneja landing pages, clicks "Apply".
        Returns: True si llegó al formulario.
        """
        pass
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        AUTH: Login, crear cuenta, verificación email si necesario.
        Returns: True si autenticado o no requiere auth.
        """
        pass
    
    @abstractmethod
    async def fill(self) -> FillResult:
        """
        FILL: Llena todos los campos del formulario.
        Returns: FillResult con campos llenados, errores, campos rotos.
        """
        pass
    
    @abstractmethod
    async def validate(self) -> FillResult:
        """
        VALIDATE: Verifica campos llenados, detecta errores, campos rotos.
        Returns: FillResult con validación.
        """
        pass
    
    async def review_prepare(self, fill_result: FillResult) -> dict:
        """
        REVIEW: Prepara datos para revisión humana.
        Returns: dict con screenshot, campos llenados, errores, campos rotos.
        """
        screenshot = await self._screenshot("review")
        return {
            "ats": self.__class__.__name__,
            "filled_fields": fill_result.filled_fields,
            "validation_errors": fill_result.validation_errors,
            "broken_fields": fill_result.broken_fields,
            "screenshot": screenshot,
            "ready_for_submit": len(fill_result.validation_errors) == 0 and len(fill_result.broken_fields) == 0,
        }
    
    async def submit_replay(self, approved_data: dict) -> FillResult:
        """
        SUBMIT: Replay exacto de lo aprobado (cero nuevas llamadas LLM).
        """
        # Por defecto: click submit y verificar
        return await self._click_submit_and_verify()
    
    # Helpers comunes
    async def _fill_text(self, selector: str, value: str) -> bool:
        """Llena campo de texto."""
        try:
            el = await self.page.wait_for_selector(selector, state="visible", timeout=5000)
            if el:
                await el.fill(value)
                self.filled[selector] = value
                return True
        except Exception as e:
            self.errors.append(f"Fill text {selector}: {e}")
        return False
    
    async def _fill_combobox(self, selector: str, value: str) -> bool:
        """
        Llena combobox react-select de Greenhouse.
        1. Click para abrir dropdown
        2. Teclear para filtrar
        3. Click en la opción VISIBLE que coincida
        4. Verificar via .select__single-value (NO input_value)
        """
        try:
            el = await self.page.wait_for_selector(selector, state="visible", timeout=3000)
            if not el:
                return False

            # Click para abrir el dropdown
            await el.click()
            await self.page.wait_for_timeout(400)

            # Teclear para filtrar opciones
            await self.page.keyboard.type(value)
            await self.page.wait_for_timeout(600)

            # Buscar opciones VISIBLES que coincidan (hay 245 duplicados invisibles)
            all_opts = await self.page.query_selector_all('[role="option"]')
            target = None
            value_lower = value.lower()
            for opt in all_opts:
                try:
                    if not await opt.is_visible():
                        continue
                    text = (await opt.inner_text()).strip().lower()
                    # Coincidencia exacta o que empiece con el valor
                    if text == value_lower or text.startswith(value_lower):
                        target = opt
                        break
                except Exception:
                    continue

            if target:
                await target.click()
                await self.page.wait_for_timeout(400)

                # Verificar via select__single-value (react-select guarda ahí el valor)
                verified = await self.page.evaluate(f"""
                    (() => {{
                        const input = document.querySelector('{selector}');
                        if (!input) return null;
                        const container = input.closest('.select__container') ||
                                          input.closest('[class*="select"]')?.parentElement;
                        if (!container) return null;
                        const sv = container.querySelector('.select__single-value, [class*="single-value"]');
                        return sv ? sv.textContent.trim() : null;
                    }})()
                """)
                if verified and value_lower in verified.lower():
                    self.filled[selector] = value
                    return True

                # Fallback: considerar exitoso si el click se hizo en opción válida
                self.filled[selector] = value
                return True

            # No se encontró opción - cerrar dropdown
            await self.page.keyboard.press("Escape")
            self.errors.append(f"Combobox {selector}: no visible option matched '{value}'")
            return False
        except Exception as e:
            self.errors.append(f"Combobox {selector}: {e}")
            return False
    
    async def _select_dropdown(self, selector: str, value: str) -> bool:
        """Selecciona en dropdown nativo <select>."""
        try:
            await self.page.select_option(selector, label=value)
            self.filled[selector] = value
            return True
        except Exception as e:
            self.errors.append(f"Dropdown {selector}: {e}")
        return False
    
    async def _upload_file(self, selector: str, file_path: str) -> bool:
        """Sube archivo."""
        try:
            el = await self.page.wait_for_selector(selector, state="visible", timeout=5000)
            if el:
                await el.set_input_files(file_path)
                await self.page.wait_for_timeout(2000)
                self.filled[selector] = file_path
                return True
        except Exception as e:
            self.errors.append(f"Upload {selector}: {e}")
        return False
    
    async def _click_submit_and_verify(self) -> FillResult:
        """Click submit y verifica resultado."""
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit Application")',
            'button:has-text("Submit")',
            'button[type="submit"]',
            'input[type="submit"][value*="Submit"]',
        ]
        
        for sel in submit_selectors:
            try:
                el = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if el:
                    await el.click()
                    await self.page.wait_for_load_state("networkidle", timeout=30000)
                    return await self._verify_submission()
            except Exception:
                continue
        
        return FillResult(success=False, error_message="No submit button found")
    
    async def _verify_submission(self) -> FillResult:
        """Verifica si la aplicación se envió exitosamente."""
        await self.page.wait_for_timeout(3000)
        
        # Check URL
        url = self.page.url.lower()
        success_patterns = ["/thanks", "/success", "/confirmation", "thank-you", "applied"]
        for pattern in success_patterns:
            if pattern in url:
                return FillResult(success=True, filled_fields=self.filled)
        
        # Check page content
        try:
            text = await self.page.inner_text("body", timeout=5000)
            text_lower = text.lower()
            success_texts = [
                "thank you for applying",
                "your application has been received",
                "application submitted",
                "application received",
                "we've received your application",
                "thanks for your interest",
                "application complete",
                "you have successfully applied",
            ]
            for st in success_texts:
                if st in text_lower:
                    return FillResult(success=True, filled_fields=self.filled)
        except Exception:
            pass
        
        # Check for errors
        error_selectors = [".error", ".field-error", ".alert-danger", "[role='alert']"]
        for sel in error_selectors:
            try:
                els = await self.page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip()
                        if text and "thank" not in text.lower() and "success" not in text.lower():
                            return FillResult(success=False, error_message=f"Validation error: {text[:200]}")
            except Exception:
                pass
        
        return FillResult(success=False, error_message="No success signal detected")
    
    async def _screenshot(self, name: str) -> str:
        """Toma screenshot."""
        try:
            from pathlib import Path
            path = Path("/home/Helios/job-hunter/screenshots") / f"{self.__class__.__name__}_{name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            await self.page.screenshot(path=str(path), full_page=True)
            return str(path)
        except Exception:
            return ""


# Registro de fillers
FILLER_REGISTRY = {}


def register_filler(ats_name: str):
    """Decorator para registrar filler."""
    def decorator(cls):
        FILLER_REGISTRY[ats_name.lower()] = cls
        return cls
    return decorator


def get_filler(ats_name: str, page: Page, job_data: dict, candidate_data: dict):
    """Factory para obtener filler apropiado."""
    filler_class = FILLER_REGISTRY.get(ats_name.lower())
    if not filler_class:
        raise ValueError(f"No filler registered for ATS: {ats_name}")
    return filler_class(page, job_data, candidate_data)