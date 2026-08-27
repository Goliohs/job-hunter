"""
Filler específico para LinkedIn Easy Apply.

LinkedIn Easy Apply usa un modal simple con campos estándar.
Ventajas:
- Sin CAPTCHA (usa tu sesión autenticada)
- Formulario modal simple
- Campos estándar consistentes
- Usa tu sesión de LinkedIn (cookies)
"""
import logging
from typing import Any
from playwright.async_api import Page
from .fillers import ATSBaseFiller, FillResult, register_filler

logger = logging.getLogger(__name__)


@register_filler("linkedin")
class LinkedInFiller(ATSBaseFiller):
    """Filler para LinkedIn Easy Apply."""
    
    async def analyze(self) -> dict:
        """Analiza modal Easy Apply."""
        try:
            # Esperar modal Easy Apply
            await self.page.wait_for_selector(
                '[data-test-modal]', 
                state="visible", 
                timeout=10000
            )
        except Exception:
            pass
        
        # Detectar campos en el modal
        fields = await self.page.query_selector_all(
            '[data-test-modal] input, [data-test-modal] select, [data-test-modal] textarea'
        )
        field_info = []
        for f in fields:
            name = await f.get_attribute("name") or await f.get_attribute("id")
            field_type = await f.get_attribute("type")
            tag = await f.evaluate("el => el.tagName.toLowerCase()")
            if name:
                field_info.append({"name": name, "type": field_type or tag, "tag": tag})
        
        return {"fields": field_info, "ats": "linkedin"}
    
    async def navigate(self) -> bool:
        """Navega y clickea Easy Apply."""
        if "linkedin.com" not in self.page.url:
            return False
        
        # Buscar botón Easy Apply
        easy_apply_selectors = [
            'button:has-text("Easy Apply")',
            'button[data-control-name="jobdetails_topcard_inapply"]',
            'button:has-text("Solicitar empleo")',
            'button:has-text("Apply")',
        ]
        
        for sel in easy_apply_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=5000)
                if btn:
                    await btn.click()
                    await self.page.wait_for_load_state("networkidle")
                    await self.page.wait_for_timeout(2000)
                    return True
            except Exception:
                continue
        return False
    
    async def authenticate(self) -> bool:
        """Verifica si está logueado en LinkedIn."""
        # Verificar si hay sesión activa
        try:
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=10000)
            await self.page.wait_for_timeout(2000)
            
            # Verificar indicadores de login
            logged_in = await self.page.query_selector(
                '[data-test-global-nav__me], .global-nav__me, .feed-identity-module'
            )
            if logged_in:
                return True
        except Exception:
            pass
        
        # No está logueado - requiere intervención humana
        logger.warning("[LinkedIn] No hay sesión activa, requiere login manual")
        return False
    
    async def fill(self) -> FillResult:
        """Llena modal Easy Apply."""
        self.filled = {}
        self.errors = []
        self.broken = []
        
        try:
            # Esperar modal
            await self.page.wait_for_selector('[data-test-modal]', state="visible", timeout=10000)
            await self.page.wait_for_timeout(1000)
            
            # Paso 1: Información básica (si es primera página)
            await self._fill_step_1()
            
            # Navegar pasos
            max_steps = 5
            for step in range(max_steps):
                # Verificar si hay botón "Next" o "Review"
                next_btn = await self._click_next_or_review()
                if not next_btn:
                    break
                
                await self.page.wait_for_load_state("networkidle")
                await self.page.wait_for_timeout(1000)
                
                # Llenar campos del paso actual
                await self._fill_current_step()
            
            # Paso final: Review y Submit
            if await self._click_review():
                await self.page.wait_for_load_state("networkidle")
                await self._fill_current_step()
                
                if await self._click_submit():
                    return FillResult(
                        success=True,
                        filled_fields=self.filled,
                        validation_errors=self.errors,
                        broken_fields=self.broken,
                    )
            
            return FillResult(
                success=len(self.errors) == 0,
                filled_fields=self.filled,
                validation_errors=self.errors,
                broken_fields=self.broken,
            )
            
        except Exception as e:
            self.errors.append(f"Fill failed: {e}")
            return FillResult(
                success=False,
                filled_fields=self.filled,
                validation_errors=self.errors,
                broken_fields=self.broken,
                error_message=str(e),
            )
    
    async def _fill_step_1(self):
        """Paso 1: Info básica (nombre, email, teléfono)."""
        full_name = f"{self.candidate_data.get('first_name', '')} {self.candidate_data.get('last_name', '')}".strip()
        
        # LinkedIn usa data-test-form-builder fields
        field_mappings = {
            'input[name="text"][data-test-text-entity-list-form-input]': full_name,
            'input[name="email"]': self.candidate_data.get("email", ""),
            'input[name="phoneNumber"]': self.candidate_data.get("phone", ""),
        }
        
        for selector, value in field_mappings.items():
            if value:
                await self._fill_text(selector, value)
        
        # Click Next si existe
        await self._click_next_or_review()
    
    async def _fill_current_step(self):
        """Llena campos del paso actual del modal."""
        # Detectar campos visibles en el modal actual
        inputs = await self.page.query_selector_all('[data-test-modal] input:visible, [data-test-modal] textarea:visible, [data-test-modal] select:visible')
        
        for inp in inputs:
            name = await inp.get_attribute("name") or await inp.get_attribute("id")
            label_text = ""
            
            # Buscar label asociado
            if name:
                label = await self.page.query_selector(f'label[for="{name}"]')
                if label:
                    label_text = (await label.inner_text()).lower()
            
            if not label_text and name:
                label_text = name.lower()
            
            value = self._get_value_for_label(label_text)
            if value:
                tag = await inp.evaluate("el => el.tagName.toLowerCase()")
                field_type = await inp.get_attribute("type")
                
                if tag == "select":
                    await self._select_dropdown(name, value)
                elif field_type == "checkbox":
                    should_check = value.lower() in ("true", "yes", "1", "sí")
                    is_checked = await inp.is_checked()
                    if is_checked != should_check:
                        await inp.click()
                        self.filled[name] = value
                else:
                    await self._fill_text(f'[name="{name}"]', value)
    
    async def _click_next_or_review(self) -> bool:
        """Click Next o Review."""
        selectors = [
            'button[aria-label="Continue to next step"]',
            'button:has-text("Next")',
            'button:has-text("Siguiente")',
            'button[data-test-modal-next-btn]',
        ]
        for sel in selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn and await btn.is_enabled():
                    await btn.click()
                    return True
            except Exception:
                continue
        return False
    
    async def _click_review(self) -> bool:
        """Click Review."""
        selectors = [
            'button[aria-label="Review your application"]',
            'button:has-text("Review")',
            'button:has-text("Revisar")',
            'button[data-test-modal-review-btn]',
        ]
        for sel in selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn and await btn.is_enabled():
                    await btn.click()
                    return True
            except Exception:
                continue
        return False
    
    async def _click_submit(self) -> bool:
        """Click Submit final."""
        selectors = [
            'button[aria-label="Submit application"]',
            'button:has-text("Submit application")',
            'button:has-text("Enviar solicitud")',
            'button[data-test-modal-submit-btn]',
        ]
        for sel in selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn and await btn.is_enabled():
                    await btn.click()
                    await self.page.wait_for_load_state("networkidle", timeout=30000)
                    return True
            except Exception:
                continue
        return False
    
    def _get_value_for_label(self, label: str) -> str:
        label_lower = label.lower()
        
        if "name" in label_lower or "nombre" in label_lower:
            return f"{self.candidate_data.get('first_name', '')} {self.candidate_data.get('last_name', '')}".strip()
        if "email" in label_lower:
            return self.candidate_data.get("email", "")
        if "phone" in label_lower or "teléfono" in label_lower:
            return self.candidate_data.get("phone", "")
        if "linkedin" in label_lower:
            return self.candidate_data.get("linkedin", "")
        if "github" in label_lower:
            return self.candidate_data.get("github", "")
        if "portfolio" in label_lower or "website" in label_lower:
            return self.candidate_data.get("portfolio", "")
        if "location" in label_lower or "ubicación" in label_lower:
            return self.candidate_data.get("location", "Remote Worldwide")
        if "visa" in label_lower or "sponsor" in label_lower:
            return "No sponsorship required"
        if "notice" in label_lower or "disponibilidad" in label_lower:
            return self.candidate_data.get("notice_period", "Immediate")
        if "salary" in label_lower or "salario" in label_lower:
            return self.candidate_data.get("salary_expectation", "Negotiable")
        if "experience" in label_lower or "experiencia" in label_lower:
            return "10+ years"
        return ""
    
    async def validate(self) -> FillResult:
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )