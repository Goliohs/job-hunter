"""
Fillers para ATS con formularios estándar y confiables:
Workable, Recruitee, Teamtailor, SmartRecruiters
"""
import logging
from typing import Any
from playwright.async_api import Page
from .fillers import ATSBaseFiller, FillResult, register_filler

logger = logging.getLogger(__name__)


@register_filler("workable")
class WorkableFiller(ATSBaseFiller):
    """Filler para Workable - formularios muy estándar."""
    
    async def analyze(self) -> dict:
        return {"ats": "workable"}
    
    async def navigate(self) -> bool:
        if "workable.com" not in self.page.url:
            return False
        return True
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        self.filled = {}
        self.errors = []
        self.broken = []
        
        # Workable usa campos con name consistentes
        await self._fill_text('input[name="candidate[name]"]', 
            f"{self.candidate_data.get('first_name', '')} {self.candidate_data.get('last_name', '')}".strip())
        await self._fill_text('input[name="candidate[email]"]', self.candidate_data.get("email", ""))
        await self._fill_text('input[name="candidate[phone]"]', self.candidate_data.get("phone", ""))
        await self._fill_text('input[name="candidate[linkedin]"]', self.candidate_data.get("linkedin", ""))
        await self._fill_text('input[name="candidate[website]"]', self.candidate_data.get("portfolio", ""))
        
        # Location
        await self._fill_text('input[name="candidate[location]"]', self.candidate_data.get("location", "Remote Worldwide"))
        
        # CV
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_file('input[name="candidate[resume]"], input[type="file"]', cv_path)
        
        # Cover letter
        cl_path = self.candidate_data.get("cover_letter_path", "")
        if cl_path:
            await self._upload_file('input[name="candidate[cover_letter]"]', cl_path)
        
        # Preguntas custom
        await self._answer_custom_questions()
        
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )
    
    async def _answer_custom_questions(self):
        """Workable preguntas custom."""
        try:
            questions = await self.page.query_selector_all('.question, [data-ui="question"]')
            for q in questions:
                label_el = q.query_selector('label, .question-label')
                label_text = (await label_el.inner_text()).lower() if label_el else ""
                
                if "visa" in label_text or "sponsor" in label_text:
                    await self._fill_text('textarea, input[type="text"]', "No sponsorship required")
                elif "notice" in label_text or "availability" in label_text:
                    await self._fill_text('textarea, input[type="text"]', "Immediate")
                elif "salary" in label_text:
                    await self._fill_text('input[type="text"], textarea', "Negotiable")
        except Exception as e:
            self.errors.append(f"Custom questions: {e}")
    
    async def validate(self) -> FillResult:
        return FillResult(success=len(self.errors) == 0, filled_fields=self.filled, 
                         validation_errors=self.errors, broken_fields=self.broken)
    
    async def navigate(self) -> bool:
        return "workable.com" in self.page.url
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        return await self.fill()
    
    async def validate(self) -> FillResult:
        return await self.validate()


@register_filler("recruitee")
class RecruiteeFiller(ATSBaseFiller):
    """Filler para Recruitee - formularios limpios y estándar."""
    
    async def analyze(self) -> dict:
        return {"ats": "recruitee"}
    
    async def navigate(self) -> bool:
        return "recruitee.com" in self.page.url
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        self.filled = {}
        self.errors = []
        self.broken = []
        
        # Recruitee usa data-attributes consistentes
        await self._fill_text('input[data-field="name"]', 
            f"{self.candidate_data.get('first_name', '')} {self.candidate_data.get('last_name', '')}".strip())
        await self._fill_text('input[data-field="email"]', self.candidate_data.get("email", ""))
        await self._fill_text('input[data-field="phone"]', self.candidate_data.get("phone", ""))
        await self._fill_text('input[data-field="linkedin"]', self.candidate_data.get("linkedin", ""))
        await self._fill_text('input[data-field="website"]', self.candidate_data.get("portfolio", ""))
        
        # CV
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_file('input[data-field="cv"], input[type="file"]', cv_path)
        
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )
    
    async def validate(self) -> FillResult:
        return FillResult(success=len(self.errors) == 0, filled_fields=self.filled,
                         validation_errors=self.errors, broken_fields=self.broken)
    
    async def navigate(self) -> bool:
        return "recruitee.com" in self.page.url
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        return await self.fill()
    
    async def validate(self) -> FillResult:
        return await self.validate()


@register_filler("teamtailor")
class TeamtailorFiller(ATSBaseFiller):
    """Filler para Teamtailor - similar a Recruitee."""
    
    async def analyze(self) -> dict:
        return {"ats": "teamtailor"}
    
    async def navigate(self) -> bool:
        return "teamtailor.com" in self.page.url
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        self.filled = {}
        self.errors = []
        self.broken = []
        
        await self._fill_text('input[name="candidate[name]"]', 
            f"{self.candidate_data.get('first_name', '')} {self.candidate_data.get('last_name', '')}".strip())
        await self._fill_text('input[name="candidate[email]"]', self.candidate_data.get("email", ""))
        await self._fill_text('input[name="candidate[phone]"]', self.candidate_data.get("phone", ""))
        await self._fill_text('input[name="candidate[linkedin]"]', self.candidate_data.get("linkedin", ""))
        await self._fill_text('input[name="candidate[website]"]', self.candidate_data.get("portfolio", ""))
        
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_file('input[name="candidate[resume]"], input[type="file"]', cv_path)
        
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )
    
    async def validate(self) -> FillResult:
        return FillResult(success=len(self.errors) == 0, filled_fields=self.filled,
                         validation_errors=self.errors, broken_fields=self.broken)
    
    async def navigate(self) -> bool:
        return "teamtailor.com" in self.page.url
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        return await self.fill()
    
    async def validate(self) -> FillResult:
        return await self.validate()


@register_filler("smartrecruiters")
class SmartRecruitersFiller(ATSBaseFiller):
    """Filler para SmartRecruiters."""
    
    async def analyze(self) -> dict:
        return {"ats": "smartrecruiters"}
    
    async def navigate(self) -> bool:
        return "smartrecruiters.com" in self.page.url
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        self.filled = {}
        self.errors = []
        self.broken = []
        
        await self._fill_text('input[name="firstName"]', self.candidate_data.get("first_name", ""))
        await self._fill_text('input[name="lastName"]', self.candidate_data.get("last_name", ""))
        await self._fill_text('input[name="email"]', self.candidate_data.get("email", ""))
        await self._fill_text('input[name="phoneNumber"]', self.candidate_data.get("phone", ""))
        await self._fill_text('input[name="linkedin"]', self.candidate_data.get("linkedin", ""))
        await self._fill_text('input[name="website"]', self.candidate_data.get("portfolio", ""))
        
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_file('input[name="resume"], input[type="file"]', cv_path)
        
        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )
    
    async def validate(self) -> FillResult:
        return FillResult(success=len(self.errors) == 0, filled_fields=self.filled,
                         validation_errors=self.errors, broken_fields=self.broken)
    
    async def navigate(self) -> bool:
        return "smartrecruiters.com" in self.page.url
    
    async def authenticate(self) -> bool:
        return True
    
    async def fill(self) -> FillResult:
        return await self.fill()
    
    async def validate(self) -> FillResult:
        return await self.validate()