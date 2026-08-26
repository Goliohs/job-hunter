"""Auto-aplicación para Ashby ATS."""
from typing import Dict, Any
from playwright.sync_api import Page


class AshbyATS:
    """Aplicación automática para Ashby."""

    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str, semi_auto: bool = False):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
        self.cover_letter_path = profile.get("cover_letter_path", "")
        self.semi_auto = semi_auto

    def apply(self, job_url: str = None) -> Dict[str, Any]:
        try:
            print(f"[ashby] Navegando a {self.job['url']}")
            self.page.goto(self.job["url"], wait_until="networkidle", timeout=60000)
            self.page.wait_for_load_state("networkidle")

            if "ashbyhq.com" not in self.page.url:
                return {"success": False, "message": "No es página de Ashby"}

            self._safe_click('button:has-text("Apply")')
            self._safe_click('a:has-text("Apply")')
            self.page.wait_for_load_state("networkidle")

            self.page.wait_for_selector('form, [data-testid="application-form"]', timeout=15000)

            if not self.fill_personal_info():
                return {"success": False, "message": "Falló info personal"}

            if not self.upload_cv():
                return {"success": False, "message": "Falló subida CV"}

            if self.cover_letter_path:
                self.upload_cover_letter()

            self.answer_custom_questions()

            if not self.submit_application():
                return {"success": False, "message": "Falló envío final"}

            return {"success": True, "message": "Aplicación enviada a Ashby", "application_id": ""}

        except Exception as e:
            return {"success": False, "message": f"Error Ashby: {e}"}

    def fill_personal_info(self) -> bool:
        p = self.profile

        fields = [
            ('input[name="name"]', p.get("first_name", "") + " " + p.get("last_name", "")),
            ('input[name="firstName"]', p.get("first_name", "")),
            ('input[name="lastName"]', p.get("last_name", "")),
            ('input[name="email"]', p.get("email", "")),
            ('input[name="phone"]', p.get("phone", "")),
            ('input[name="linkedin"]', p.get("linkedin", "")),
            ('input[name="github"]', p.get("github", "")),
            ('input[name="portfolio"]', p.get("portfolio", "")),
            ('input[name="location"]', p.get("location", "")),
        ]

        for selector, value in fields:
            if value:
                self._safe_fill(selector, value)

        self._safe_click('button:has-text("Continue")')
        self._safe_click('button[data-testid="continue-button"]')
        self.page.wait_for_load_state("networkidle")

        return True

    def upload_cv(self) -> bool:
        selectors = [
            'input[data-testid="resume-upload"]',
            'input[name="resume"]',
            'input[type="file"][accept*="pdf"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            if self._safe_upload(sel, self.cv_path):
                self.page.wait_for_timeout(3000)
                return True
        return False

    def upload_cover_letter(self) -> bool:
        if not self.cover_letter_path:
            return True
        selectors = [
            'input[data-testid="cover-letter-upload"]',
            'input[name="coverLetter"]',
            'input[type="file"][accept*="pdf"]:not([name="resume"])',
        ]
        for sel in selectors:
            if self._safe_upload(sel, self.cover_letter_path):
                self.page.wait_for_timeout(2000)
                return True
        return False

    def answer_custom_questions(self) -> bool:
        questions = self.page.query_selector_all('[data-testid="question"], .custom-question')
        for q in questions:
            label = q.query_selector('label, [data-testid="question-label"]')
            label_text = label.inner_text().lower() if label else ""

            if "visa" in label_text or "authorization" in label_text:
                self._safe_fill('textarea, input[type="text"]', self.profile.get("visa_status", ""), root=q)
            elif "notice" in label_text or "availability" in label_text:
                self._safe_fill('textarea, input[type="text"]', self.profile.get("notice_period", ""), root=q)
            elif "salary" in label_text or "compensation" in label_text:
                self._safe_fill('input[type="text"], textarea', self.profile.get("salary_expectation", ""), root=q)

        self._safe_click('button:has-text("Continue")')
        self._safe_click('button:has-text("Submit")')
        self.page.wait_for_load_state("networkidle")
        return True

    def submit_application(self) -> bool:
        return (
            self._safe_click('button:has-text("Submit application")') or
            self._safe_click('button[data-testid="submit-button"]') or
            self._safe_click('button:has-text("Submit")')
        )

    def _safe_fill(self, selector: str, value: str, root=None) -> bool:
        if not value:
            return False
        try:
            page_or_root = root if root else self.page
            el = page_or_root.query_selector(selector)
            if el and el.is_visible():
                el.fill(value)
                return True
        except Exception:
            pass
        return False

    def _safe_click(self, selector: str, timeout: int = 5000) -> bool:
        try:
            el = self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            if el:
                el.click()
                return True
        except Exception:
            pass
        return False

    def _safe_upload(self, selector: str, file_path: str, timeout: int = 10000) -> bool:
        try:
            from pathlib import Path
            path = Path(file_path).resolve()
            if not path.exists():
                print(f"[ashby] File not found: {path}")
                return False
            self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            self.page.set_input_files(selector, str(path))
            return True
        except Exception as e:
            print(f"[ashby] Upload failed on {selector}: {e}")
        return False