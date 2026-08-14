"""Auto-aplicación para Ashby ATS."""
from auto_apply.base import ATSBase, CandidateProfile
from typing import Dict, Any


class AshbyATS(ATSBase):
    """Aplicación automática para Ashby."""

    def apply(self, job_url: str) -> Dict[str, Any]:
        self.setup_browser()
        try:
            print(f"[ashby] Navegando a {job_url}")
            self.page.goto(job_url, wait_until="networkidle", timeout=60000)
            self.wait_for_navigation()

            if "ashbyhq.com" not in self.page.url:
                return {"success": False, "message": "No es página de Ashby"}

            # Ashby: botón "Apply" suele estar visible
            self.safe_click('button:has-text("Apply")')
            self.safe_click('a:has-text("Apply")')
            self.wait_for_navigation()

            # Esperar formulario Ashby
            self.page.wait_for_selector('form, [data-testid="application-form"]', timeout=15000)

            if not self.fill_personal_info():
                return {"success": False, "message": "Falló info personal"}

            if not self.upload_cv():
                return {"success": False, "message": "Falló subida CV"}

            if self.profile.cover_letter_path:
                self.upload_cover_letter()

            self.answer_custom_questions()

            # En multi-step, answer_custom_questions ya hace click en Continue/Submit
            # En semi-auto, NO hacer submit final
            if self.semi_auto:
                print("[ashby] SEMI-AUTO: esperando humano para submit final")
                result = self.wait_for_human_submit(timeout=600)
                return result

            if not self.submit_application():
                return {"success": False, "message": "Falló envío final"}

            return {"success": True, "message": "Aplicación enviada a Ashby", "application_id": ""}

        except Exception as e:
            return {"success": False, "message": f"Error Ashby: {e}"}
        finally:
            self.close_browser()

    def fill_personal_info(self) -> bool:
        p = self.profile

        # Ashby usa campos con data-testid o name específicos
        fields = [
            ('input[name="name"]', p.full_name),
            ('input[name="firstName"]', p.full_name.split()[0] if p.full_name else ""),
            ('input[name="lastName"]', " ".join(p.full_name.split()[1:]) if len(p.full_name.split()) > 1 else ""),
            ('input[name="email"]', p.email),
            ('input[name="phone"]', p.phone),
            ('input[name="linkedin"]', p.linkedin),
            ('input[name="github"]', p.github),
            ('input[name="portfolio"]', p.portfolio),
            ('input[name="location"]', p.location),
        ]

        for selector, value in fields:
            if value:
                self.safe_fill(selector, value)

        # Click Continue
        self.safe_click('button:has-text("Continue")')
        self.safe_click('button[data-testid="continue-button"]')
        self.wait_for_navigation()

        return True

    def upload_cv(self) -> bool:
        selectors = [
            'input[data-testid="resume-upload"]',
            'input[name="resume"]',
            'input[type="file"][accept*="pdf"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            if self.safe_upload(sel, self.profile.cv_path):
                self.page.wait_for_timeout(3000)
                return True
        return False

    def upload_cover_letter(self) -> bool:
        if not self.profile.cover_letter_path:
            return True
        selectors = [
            'input[data-testid="cover-letter-upload"]',
            'input[name="coverLetter"]',
            'input[type="file"][accept*="pdf"]:not([name="resume"])',
        ]
        for sel in selectors:
            if self.safe_upload(sel, self.profile.cover_letter_path):
                self.page.wait_for_timeout(2000)
                return True
        return False

    def answer_custom_questions(self) -> bool:
        # Ashby preguntas custom
        questions = self.page.query_selector_all('[data-testid="question"], .custom-question')
        for q in questions:
            label = q.query_selector('label, [data-testid="question-label"]')
            label_text = label.inner_text().lower() if label else ""

            if "visa" in label_text or "authorization" in label_text:
                self.safe_fill('textarea, input[type="text"]', self.profile.visa_status, root=q)
            elif "notice" in label_text or "availability" in label_text:
                self.safe_fill('textarea, input[type="text"]', self.profile.notice_period, root=q)
            elif "salary" in label_text or "compensation" in label_text:
                self.safe_fill('input[type="text"], textarea', self.profile.salary_expectation, root=q)

        # Navegar steps si es multi-step
        if not self.semi_auto:
            self.safe_click('button:has-text("Continue")')
            self.safe_click('button:has-text("Submit")')
            self.wait_for_navigation()
        else:
            # En semi-auto solo Continue, no Submit
            self.safe_click('button:has-text("Continue")')
            self.wait_for_navigation()
        return True

    def submit_application(self) -> bool:
        if self.semi_auto:
            return True
        return (
            self.safe_click('button:has-text("Submit application")') or
            self.safe_click('button[data-testid="submit-button"]') or
            self.safe_click('button:has-text("Submit")')
        )