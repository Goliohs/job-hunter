"""
Filler específico para Lever ATS.

Lever usa estructura consistente:
- Formulario directo o iframe
- Campos con name="firstName", name="lastName", etc.
- Comboboxes React para dropdowns
- Preguntas custom en secciones .question-field
"""
import logging
from typing import Any
from playwright.async_api import Page
from .fillers import ATSBaseFiller, FillResult, register_filler

logger = logging.getLogger(__name__)


@register_filler("lever")
class LeverFiller(ATSBaseFiller):
    """Filler especializado para Lever."""
    
    async def analyze(self) -> dict:
        """Analiza estructura Lever."""
        # Esperar formulario
        try:
            await self.page.wait_for_selector('form, [data-qa="application-form"]', timeout=10000)
        except Exception:
            pass
        
        # Detectar campos
        fields = await self.page.query_selector_all('input, select, textarea')
        field_info = []
        for f in fields:
            name = await f.get_attribute("name")
            field_type = await f.get_attribute("type")
            tag = await f.evaluate("el => el.tagName.toLowerCase()")
            if name:
                field_info.append({"name": name, "type": field_type or tag, "tag": tag})
        
        return {"fields": field_info, "ats": "lever"}
    
    async def navigate(self) -> bool:
        """Navega y clickea Apply si está en landing page."""
        if "lever.co" not in self.page.url:
            return False
        
        # Click Apply buttons
        apply_selectors = [
            'a:has-text("Apply for this job")',
            'button:has-text("Apply")',
            'a[data-qa="apply-button"]',
        ]
        for sel in apply_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn:
                    await btn.click()
                    await self.page.wait_for_load_state("networkidle")
                    return True
            except Exception:
                continue
        return True  # Puede que ya esté en formulario
    
    async def authenticate(self) -> bool:
        """Lever no requiere login para aplicar."""
        return True
    
    async def fill(self) -> FillResult:
        """Llena formulario Lever."""
        self.filled = {}
        self.errors = []
        self.broken = []
        
        # 1. Nombre completo y split
        full_name = f"{self.candidate_data.get('first_name', '')} {self.candidate_data.get('last_name', '')}".strip()
        await self._fill_text('input[name="name"]', full_name)
        await self._fill_text('input[name="firstName"]', self.candidate_data.get("first_name", ""))
        await self._fill_text('input[name="lastName"]', self.candidate_data.get("last_name", ""))
        
        # 2. Email y teléfono
        await self._fill_text('input[name="email"]', self.candidate_data.get("email", ""))
        await self._fill_text('input[type="email"]', self.candidate_data.get("email", ""))
        await self._fill_text('input[name="phone"]', self.candidate_data.get("phone", ""))
        await self._fill_text('input[type="tel"]', self.candidate_data.get("phone", ""))
        
        # 3. LinkedIn, GitHub, Portfolio
        await self._fill_text('input[name="linkedin"]', self.candidate_data.get("linkedin", ""))
        await self._fill_text('input[name="urls[LinkedIn]"]', self.candidate_data.get("linkedin", ""))
        await self._fill_text('input[name="github"]', self.candidate_data.get("github", ""))
        await self._fill_text('input[name="urls[GitHub]"]', self.candidate_data.get("github", ""))
        await self._fill_text('input[name="portfolio"]', self.candidate_data.get("portfolio", ""))
        await self._fill_text('input[name="urls[Portfolio]"]', self.candidate_data.get("portfolio", ""))
        
        # 4. Ubicación
        await self._fill_text('input[name="location"]', self.candidate_data.get("location", "Remote Worldwide"))
        
        # 5. Click Continue/Next
        await self._click_continue()
        
        # 6. Subir CV
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_cv()
        
        # 7. Cover letter
        cl_path = self.candidate_data.get("cover_letter_path", "")
        if cl_path:
            await self._upload_cover_letter()
        
        # 8. Preguntas custom
        await self._answer_custom_questions()
        
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )
    
    async def _click_continue(self):
        """Click en botón Continue/Next."""
        continue_selectors = [
            'button:has-text("Continue")',
            'button:has-text("Next")',
            'button[type="submit"]:has-text("Continue")',
            'button[data-qa="continue-button"]',
        ]
        for sel in continue_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn:
                    await btn.click()
                    await self.page.wait_for_load_state("networkidle")
                    return True
            except Exception:
                continue
        return False
    
    async def _upload_cv(self):
        """Sube CV en Lever."""
        cv_path = self.candidate_data.get("cv_path", "")
        if not cv_path:
            return
        
        selectors = [
            'input[type="file"][accept*="pdf"]',
            'input[name="resume"]',
            'input[data-qa="resume-upload"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            try:
                el = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if el:
                    await el.set_input_files(cv_path)
                    await self.page.wait_for_timeout(2000)
                    self.filled["resume"] = cv_path
                    return True
            except Exception:
                continue
        return False
    
    async def _upload_cover_letter(self):
        """Sube cover letter."""
        cl_path = self.candidate_data.get("cover_letter_path", "")
        if not cl_path:
            return
        
        selectors = [
            'input[name="coverLetter"]',
            'input[name="cover_letter"]',
            'input[type="file"][accept*="pdf"]:not([name="resume"])',
        ]
        for sel in selectors:
            try:
                el = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if el:
                    await el.set_input_files(cl_path)
                    await self.page.wait_for_timeout(2000)
                    self.filled["cover_letter"] = cl_path
                    return True
            except Exception:
                continue
        return False
    
    async def _answer_custom_questions(self):
        """Responde preguntas custom de Lever."""
        try:
            questions = await self.page.query_selector_all('[data-qa="question"], .question-field, .custom-question')
            for q in questions:
                label_el = q.query_selector('label, .question-label')
                label_text = (await label_el.inner_text()).lower() if label_el else ""
                
                # Mapear preguntas conocidas
                if "visa" in label_text or "work authorization" in label_text:
                    await self._fill_text('textarea, input[type="text"]', self.candidate_data.get("visa_status", "No visa required"))
                elif "notice" in label_text or "availability" in label_text:
                    await self._fill_text('textarea, input[type="text"]', self.candidate_data.get("notice_period", "Immediate"))
                elif "salary" in label_text or "compensation" in label_text:
                    await self._fill_text('input[type="text"], textarea', self.candidate_data.get("salary_expectation", "Negotiable"))
                elif "linkedin" in label_text:
                    await self._fill_text('input[type="url"], input[type="text"]', self.candidate_data.get("linkedin", ""))
                elif "github" in label_text:
                    await self._fill_text('input[type="url"], input[type="text"]', self.candidate_data.get("github", ""))
                
                # Dropdowns
                selects = await q.query_selector_all('select')
                for sel in selects:
                    try:
                        opts = await sel.query_selector_all('option')
                        for opt in opts:
                            opt_text = (await opt.inner_text()).lower()
                            if any(kw in opt_text for kw in ["yes", "no", "remote", "hybrid", "no sponsorship"]):
                                await sel.select_option(value=await opt.get_attribute("value"))
                                break
                    except Exception:
                        pass
        except Exception as e:
            self.errors.append(f"Custom questions: {e}")
    
    async def validate(self) -> FillResult:
        """Valida formulario Lever."""
        self.errors = []
        self.broken = []
        
        # Verificar errores visibles
        error_selectors = [".error", ".field-error", "[data-qa='error-message']", "[role='alert']"]
        for sel in error_selectors:
            try:
                els = await self.page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip()
                        if text and "thank" not in text.lower():
                            self.errors.append(text[:200])
            except Exception:
                pass
        
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )
    
    async def navigate(self) -> bool:
        if "lever.co" not in self.page.url:
            return False
        return True  # Ya manejado en fill
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        # Llamar a fill principal
        return await self.fill()
    
    async def validate(self) -> FillResult:
        # Ya definido arriba
        return await self.validate()