"""Auto-aplicación para Lever ATS."""
from typing import Dict, Any
from playwright.sync_api import Page


class LeverATS:
    """Aplicación automática para Lever."""

    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
        self.cover_letter_path = profile.get("cover_letter_path", "")

    def apply(self, job_url: str = None) -> Dict[str, Any]:
        try:
            print(f"[lever] Navegando a {self.job['url']}")
            self.page.goto(self.job["url"], wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
            self.page.wait_for_load_state("networkidle")

            if "lever.co" not in self.page.url:
                return {"success": False, "message": "No es página de Lever"}

            self._safe_click('a:has-text("Apply for this job")')
            self._safe_click('button:has-text("Apply")')
            self.page.wait_for_load_state("networkidle")

            if not self.fill_personal_info():
                return {"success": False, "message": "Falló info personal"}

            if not self.upload_cv():
                return {"success": False, "message": "Falló subida CV"}

            if self.cover_letter_path:
                self.upload_cover_letter()

            self.answer_custom_questions()

            result = self.submit_application()
            return result

        except Exception as e:
            return {"success": False, "message": f"Error Lever: {e}"}

    def fill_personal_info(self) -> bool:
        p = self.profile

        self.page.wait_for_selector('form, [data-qa="application-form"]', timeout=10000)

        self._safe_fill('input[name="name"]', p.get("first_name", "") + " " + p.get("last_name", ""))
        self._safe_fill('input[name="firstName"]', p.get("first_name", ""))
        self._safe_fill('input[name="lastName"]', p.get("last_name", ""))

        self._safe_fill('input[name="email"]', p.get("email", ""))
        self._safe_fill('input[type="email"]', p.get("email", ""))

        self._safe_fill('input[name="phone"]', p.get("phone", ""))
        self._safe_fill('input[type="tel"]', p.get("phone", ""))

        self._safe_fill('input[name="linkedin"]', p.get("linkedin", ""))
        self._safe_fill('input[name="urls[LinkedIn]"]', p.get("linkedin", ""))

        self._safe_fill('input[name="github"]', p.get("github", ""))
        self._safe_fill('input[name="urls[GitHub]"]', p.get("github", ""))

        self._safe_fill('input[name="portfolio"]', p.get("portfolio", ""))
        self._safe_fill('input[name="urls[Portfolio]"]', p.get("portfolio", ""))

        self._safe_fill('input[name="location"]', p.get("location", ""))

        self._safe_click('button:has-text("Continue")')
        self._safe_click('button:has-text("Next")')
        self._safe_click('button[type="submit"]:has-text("Continue")')
        self.page.wait_for_load_state("networkidle")

        return True

    def upload_cv(self) -> bool:
        selectors = [
            'input[type="file"][accept*="pdf"]',
            'input[name="resume"]',
            'input[data-qa="resume-upload"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            if self._safe_upload(sel, self.cv_path):
                self.page.wait_for_timeout(2000)
                return True
        return False

    def upload_cover_letter(self) -> bool:
        if not self.cover_letter_path:
            return True
        selectors = [
            'input[name="coverLetter"]',
            'input[name="cover_letter"]',
            'input[type="file"][accept*="pdf"]:not([name="resume"])',
        ]
        for sel in selectors:
            if self._safe_upload(sel, self.cover_letter_path):
                self.page.wait_for_timeout(2000)
                return True
        return False

    def answer_custom_questions(self) -> bool:
        questions = self.page.query_selector_all('[data-qa="question"], .question-field, .custom-question')
        for q in questions:
            label = q.query_selector('label, .question-label')
            label_text = label.inner_text().lower() if label else ""

            if "visa" in label_text or "work authorization" in label_text:
                self._safe_fill('textarea, input[type="text"]', self.profile.get("visa_status", ""), root=q)
            elif "notice" in label_text or "availability" in label_text:
                self._safe_fill('textarea, input[type="text"]', self.profile.get("notice_period", ""), root=q)
            elif "salary" in label_text or "compensation" in label_text:
                self._safe_fill('input[type="text"], textarea', self.profile.get("salary_expectation", ""), root=q)
            elif "linkedin" in label_text:
                self._safe_fill('input[type="url"], input[type="text"]', self.profile.get("linkedin", ""), root=q)
            elif "github" in label_text:
                self._safe_fill('input[type="url"], input[type="text"]', self.profile.get("github", ""), root=q)

            selects = q.query_selector_all('select')
            for sel in selects:
                options = sel.query_selector_all('option')
                for opt in options:
                    if any(kw in opt.inner_text().lower() for kw in ["yes", "no", "remote", "hybrid"]):
                        sel.select_option(value=opt.get_attribute("value"))
                        break

        return True

    def submit_application(self) -> Dict[str, Any]:
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button[type="submit"]:has-text("Apply")',
            'button[data-qa="submit-application"]',
        ]
        for sel in submit_selectors:
            if self._safe_click(sel):
                print(f"[lever] Clicked submit: {sel}")
                self.page.wait_for_timeout(3000)
                self.page.wait_for_load_state("networkidle")
                result = self._verify_submission_success()
                return result

        return {"success": False, "message": "No submit button found"}

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
                print(f"[lever] File not found: {path}")
                return False
            self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            self.page.set_input_files(selector, str(path))
            return True
        except Exception as e:
            print(f"[lever] Upload failed on {selector}: {e}")
        return False

    def _verify_submission_success(self) -> Dict[str, Any]:
        import re
        self.page.wait_for_timeout(2000)

        current_url = self.page.url.lower()
        success_url_patterns = ["/thanks", "/success", "/confirmation", "thank-you", "applied"]
        for pattern in success_url_patterns:
            if pattern in current_url:
                app_id_match = re.search(r'application[/=]?(\d+)', current_url)
                app_id = app_id_match.group(1) if app_id_match else ""
                return {
                    "success": True,
                    "application_id": app_id,
                    "message": f"Success detected via URL: {self.page.url}",
                }

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
        try:
            page_text = self.page.inner_text("body", timeout=5000).lower()
            for text in success_texts:
                if text in page_text:
                    return {
                        "success": True,
                        "application_id": "",
                        "message": f"Success detected via text: '{text}'",
                    }
        except Exception:
            pass

        success_selectors = [
            '[data-qa="success-message"]',
            '.success-message',
            '.confirmation-message',
            '.application-success',
            '.submitted-confirmation',
            '[role="alert"]:has-text("success")',
            '[role="alert"]:has-text("thank")',
        ]
        for selector in success_selectors:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    return {
                        "success": True,
                        "application_id": "",
                        "message": f"Success detected via element: {selector}",
                    }
            except Exception:
                continue

        return {
            "success": False,
            "application_id": "",
            "message": "No success or error signal detected after submit",
        }