"""
Filler específico para Ashby ATS.

Ashby usa multi-step wizard con data-testid attributes.
"""
import logging
from typing import Any
from playwright.async_api import Page
from .fillers import ATSBaseFiller, FillResult, register_filler

logger = logging.getLogger(__name__)


@register_filler("ashby")
class AshbyFiller(ATSBaseFiller):
    """Filler especializado para Ashby."""
    
    async def analyze(self) -> dict:
        """Analiza estructura Ashby."""
        try:
            await self.page.wait_for_selector('[data-testid="application-form"], form', timeout=15000)
        except Exception:
            pass
        
        steps = await self.page.query_selector_all('[data-testid="step"], .step-indicator')
        return {"steps_found": len(steps), "ats": "ashby"}
    
    async def navigate(self) -> bool:
        """Navega y clickea Apply."""
        if "ashbyhq.com" not in self.page.url:
            return False
        
        apply_selectors = [
            'button:has-text("Apply")',
            'a:has-text("Apply")',
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
        return True
    
    async def authenticate(self) -> bool:
        """Ashby puede requerir login."""
        # Verificar si hay login
        login_btn = await self.page.query_selector('button:has-text("Sign in"), a:has-text("Sign in")')
        if login_btn:
            # En semi-auto, esperar a que el humano haga login
            return False
        return True
    
    async def fill(self) -> FillResult:
        """Llena formulario Ashby multi-step."""
        self.filled = {}
        self.errors = []
        self.broken = []
        
        max_steps = 5
        for step in range(max_steps):
            # Llenar página actual
            await self._fill_current_step()
            
            # Click Continue/Submit
            if step == max_steps - 1:
                # Último paso - Submit
                submitted = await self._click_submit()
                if submitted:
                    break
            else:
                # Click Continue
                continued = await self._click_continue()
                if not continued:
                    self.errors.append(f"Step {step+1}: No continue button found")
                    break
                
                await self.page.wait_for_load_state("networkidle")
        
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )
    
    async def _fill_current_step(self):
        """Llena campos de la página actual."""
        # Nombre completo
        full_name = f"{self.candidate_data.get('first_name', '')} {self.candidate_data.get('last_name', '')}".strip()
        name_fields = [
            ('input[name="name"]', full_name),
            ('input[name="firstName"]', self.candidate_data.get("first_name", "")),
            ('input[name="lastName"]', self.candidate_data.get("last_name", "")),
        ]
        for selector, value in name_fields:
            if value:
                await self._fill_text(selector, value)
        
        # Email, teléfono
        await self._fill_text('input[name="email"]', self.candidate_data.get("email", ""))
        await self._fill_text('input[name="phone"]', self.candidate_data.get("phone", ""))
        
        # LinkedIn, GitHub, Portfolio
        await self._fill_text('input[name="linkedin"]', self.candidate_data.get("linkedin", ""))
        await self._fill_text('input[name="github"]', self.candidate_data.get("github", ""))
        await self._fill_text('input[name="portfolio"]', self.candidate_data.get("portfolio", ""))
        await self._fill_text('input[name="location"]', self.candidate_data.get("location", "Remote Worldwide"))
        
        # Preguntas custom (visa, notice, salary)
        await self._answer_custom_questions()
        
        # Subir CV
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_cv()
    
    async def _answer_custom_questions(self):
        """Responde preguntas custom Ashby."""
        try:
            questions = await self.page.query_selector_all('[data-testid="question"], .custom-question')
            for q in questions:
                label_el = q.query_selector('label, [data-testid="question-label"]')
                label_text = (await label_el.inner_text()).lower() if label_el else ""
                
                if "visa" in label_text or "authorization" in label_text:
                    await self._fill_text('textarea, input[type="text"]', self.candidate_data.get("visa_status", "No visa required"))
                elif "notice" in label_text or "availability" in label_text:
                    await self._fill_text('textarea, input[type="text"]', self.candidate_data.get("notice_period", "Immediate"))
                elif "salary" in label_text or "compensation" in label_text:
                    await self._fill_text('input[type="text"], textarea', self.candidate_data.get("salary_expectation", "Negotiable"))
        except Exception as e:
            self.errors.append(f"Custom questions: {e}")
    
    async def _upload_cv(self):
        """Sube CV en Ashby."""
        cv_path = self.candidate_data.get("cv_path", "")
        if not cv_path:
            return
        
        selectors = [
            'input[data-testid="resume-upload"]',
            'input[name="resume"]',
            'input[type="file"][accept*="pdf"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            try:
                el = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if el:
                    await el.set_input_files(cv_path)
                    await self.page.wait_for_timeout(3000)
                    self.filled["resume"] = cv_path
                    return True
            except Exception:
                continue
        return False
    
    async def _click_continue(self) -> bool:
        """Click Continue/Next."""
        selectors = [
            'button:has-text("Continue")',
            'button[data-testid="continue-button"]',
            'button:has-text("Next")',
        ]
        for sel in selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn:
                    await btn.click()
                    return True
            except Exception:
                continue
        return False
    
    async def _click_submit(self) -> bool:
        """Click Submit final."""
        selectors = [
            'button:has-text("Submit application")',
            'button[data-testid="submit-button"]',
            'button:has-text("Submit")',
        ]
        for sel in selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn:
                    await btn.click()
                    await self.page.wait_for_load_state("networkidle", timeout=30000)
                    return True
            except Exception:
                continue
        return False
    
    async def validate(self) -> FillResult:
        """Valida formulario Ashby."""
        self.errors = []
        self.broken = []
        
        error_selectors = [".error", ".field-error", "[data-testid='error-message']", "[role='alert']"]
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
        if "ashbyhq.com" not in self.page.url:
            return False
        return True
    
    async def authenticate(self) -> bool:
        return True
    
    async def validate(self) -> FillResult:
        return await self.validate()