"""Auto-aplicación para Lever ATS."""
from auto_apply.base import ATSBase, CandidateProfile
from typing import Dict, Any


class LeverATS(ATSBase):
    """Aplicación automática para Lever."""

    def apply(self, job_url: str) -> Dict[str, Any]:
        self.setup_browser()
        try:
            print(f"[lever] Navegando a {job_url}")
            self.page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
            self.wait_for_navigation()

            # Verificar que es página de Lever
            if "lever.co" not in self.page.url:
                return {"success": False, "message": "No es página de Lever"}

            # Click "Apply for this job" si existe
            self.safe_click('a:has-text("Apply for this job")')
            self.safe_click('button:has-text("Apply")')
            self.wait_for_navigation()

            # Paso 1: Info personal
            if not self.fill_personal_info():
                return {"success": False, "message": "Falló info personal"}

            # Paso 2: CV
            if not self.upload_cv():
                return {"success": False, "message": "Falló subida CV"}

            # Paso 3: Cover letter
            if self.profile.cover_letter_path:
                self.upload_cover_letter()

            # Paso 4: Preguntas custom
            self.answer_custom_questions()

            # Paso 5: Submit
            result = self.submit_application()
            if result["success"]:
                return {
                    "success": True,
                    "message": result["message"],
                    "application_id": result.get("application_id", ""),
                }
            else:
                return {
                    "success": False,
                    "message": result["message"],
                }

        except Exception as e:
            return {"success": False, "message": f"Error Lever: {e}"}
        finally:
            self.close_browser()

    def fill_personal_info(self) -> bool:
        """Rellena formulario Lever."""
        p = self.profile

        # Lever usa iframe o form directo
        # Esperar formulario
        self.page.wait_for_selector('form, [data-qa="application-form"]', timeout=10000)

        # Nombre completo (Lever a veces lo splittea)
        self.safe_fill('input[name="name"]', p.full_name)
        self.safe_fill('input[name="firstName"]', p.full_name.split()[0] if p.full_name else "")
        self.safe_fill('input[name="lastName"]', " ".join(p.full_name.split()[1:]) if len(p.full_name.split()) > 1 else "")

        # Email
        self.safe_fill('input[name="email"]', p.email)
        self.safe_fill('input[type="email"]', p.email)

        # Teléfono
        self.safe_fill('input[name="phone"]', p.phone)
        self.safe_fill('input[type="tel"]', p.phone)

        # LinkedIn
        self.safe_fill('input[name="linkedin"]', p.linkedin)
        self.safe_fill('input[name="urls[LinkedIn]"]', p.linkedin)

        # GitHub
        self.safe_fill('input[name="github"]', p.github)
        self.safe_fill('input[name="urls[GitHub]"]', p.github)

        # Portfolio
        self.safe_fill('input[name="portfolio"]', p.portfolio)
        self.safe_fill('input[name="urls[Portfolio]"]', p.portfolio)

        # Ubicación
        self.safe_fill('input[name="location"]', p.location)

        # Click siguiente/continuar
        self.safe_click('button:has-text("Continue")')
        self.safe_click('button:has-text("Next")')
        self.safe_click('button[type="submit"]:has-text("Continue")')
        self.wait_for_navigation()

        return True

    def upload_cv(self) -> bool:
        """Sube CV en Lever."""
        # Lever: input[type="file"] con accept=".pdf,.doc,.docx"
        selectors = [
            'input[type="file"][accept*="pdf"]',
            'input[name="resume"]',
            'input[data-qa="resume-upload"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            if self.safe_upload(sel, self.profile.cv_path):
                self.page.wait_for_timeout(2000)  # Esperar upload
                return True
        return False

    def upload_cover_letter(self) -> bool:
        """Sube cover letter en Lever."""
        if not self.profile.cover_letter_path:
            return True
        selectors = [
            'input[name="coverLetter"]',
            'input[name="cover_letter"]',
            'input[type="file"][accept*="pdf"]:not([name="resume"])',
        ]
        for sel in selectors:
            if self.safe_upload(sel, self.profile.cover_letter_path):
                self.page.wait_for_timeout(2000)
                return True
        return False

    def answer_custom_questions(self) -> bool:
        """Responde preguntas custom de Lever (textareas, selects, radios)."""
        # Buscar todos los campos de pregunta
        questions = self.page.query_selector_all('[data-qa="question"], .question-field, .custom-question')
        for q in questions:
            label = q.query_selector('label, .question-label')
            label_text = label.inner_text().lower() if label else ""

            # Mapear preguntas conocidas a respuestas del perfil
            if "visa" in label_text or "work authorization" in label_text:
                self.safe_fill('textarea, input[type="text"]', self.profile.visa_status, root=q)
            elif "notice" in label_text or "availability" in label_text:
                self.safe_fill('textarea, input[type="text"]', self.profile.notice_period, root=q)
            elif "salary" in label_text or "compensation" in label_text:
                self.safe_fill('input[type="text"], textarea', self.profile.salary_expectation, root=q)
            elif "linkedin" in label_text:
                self.safe_fill('input[type="url"], input[type="text"]', self.profile.linkedin, root=q)
            elif "github" in label_text:
                self.safe_fill('input[type="url"], input[type="text"]', self.profile.github, root=q)

            # Selects (dropdowns)
            selects = q.query_selector_all('select')
            for sel in selects:
                options = sel.query_selector_all('option')
                for opt in options:
                    if any(kw in opt.inner_text().lower() for kw in ["yes", "no", "remote", "hybrid"]):
                        sel.select_option(value=opt.get_attribute("value"))
                        break

        return True

    def submit_application(self) -> Dict[str, Any]:
        """Envía aplicación final en Lever y verifica resultado."""
        # Modo semi-auto: NO hacer click en submit, esperar al humano
        if self.semi_auto:
            print("[lever] SEMI-AUTO: No se hará submit. Esperando humano...")
            return self.wait_for_human_submit(timeout=600)

        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
            'button[type="submit"]:has-text("Apply")',
            'button[data-qa="submit-application"]',
        ]
        for sel in submit_selectors:
            if self.safe_click(sel):
                print(f"[lever] Clicked submit: {sel}")
                self.page.wait_for_timeout(3000)
                self.wait_for_navigation()
                result = self.verify_submission_success()
                return result

        return {"success": False, "message": "No submit button found"}