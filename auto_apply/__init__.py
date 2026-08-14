"""Auto-aplicación a ATS (Lever, Greenhouse, Ashby) con Playwright."""
import os
import sys
from pathlib import Path
from typing import Dict, Optional
from playwright.sync_api import sync_playwright, Browser, Page, Playwright

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import get_conn, init_db


class BaseATS:
    """Clase base para ATS."""

    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
        self.applied = False

    def fill_personal_info(self):
        """Llena info personal común."""
        p = self.profile
        page = self.page

        # Nombre
        self.safe_fill('input[name*="first"]', p.get("first_name", ""))
        self.safe_fill('input[name*="last"]', p.get("last_name", ""))

        # Email
        self.safe_fill('input[type="email"], input[name*="email"]', p.get("email", ""))

        # Teléfono
        self.safe_fill('input[type="tel"], input[name*="phone"]', p.get("phone", ""))

        # LinkedIn
        self.safe_fill('input[name*="linkedin"]', p.get("linkedin", ""))

        # GitHub
        self.safe_fill('input[name*="github"]', p.get("github", ""))

        # Portfolio/Website
        self.safe_fill('input[name*="portfolio"], input[name*="website"]', p.get("portfolio", ""))

    def upload_cv(self):
        """Sube CV."""
        page = self.page
        file_inputs = page.query_selector_all('input[type="file"]')
        for inp in file_inputs:
            if inp.is_visible():
                inp.set_input_files(self.cv_path)
                return True
        return False

    def answer_common_questions(self):
        """Responde preguntas comunes (visa, remote, notice period)."""
        page = self.page

        # Preguntas típicas con selects
        selects = page.query_selector_all('select')
        for sel in selects:
            label = ""
            # Buscar label asociado
            parent = sel.query_selector("xpath=..")
            if parent:
                label = parent.inner_text().lower()

            options = sel.query_selector_all("option")
            for opt in options:
                text = opt.inner_text().lower()
                val = opt.get_attribute("value")

                # Visa sponsorship
                if "visa" in label or "sponsor" in label:
                    if "no" in text or "not required" in text:
                        sel.select_option(value=val)
                        break

                # Remote preference
                if "remote" in label or "location" in label:
                    if "remote" in text or "anywhere" in text:
                        sel.select_option(value=val)
                        break

                # Notice period
                if "notice" in label or "availability" in label:
                    if "immediate" in text or "0" in text or "1 week" in text:
                        sel.select_option(value=val)
                        break

    def safe_fill(self, selector: str, value: str) -> bool:
        """Fill seguro."""
        if not value:
            return False
        try:
            el = self.page.query_selector(selector)
            if el and el.is_visible():
                el.fill(value)
                return True
        except Exception:
            pass
        return False

    def safe_click(self, selector: str, timeout: int = 5000) -> bool:
        """Click seguro."""
        try:
            el = self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            if el:
                el.click()
                return True
        except Exception:
            pass
        return False

    def wait_for_navigation(self, timeout: int = 30000):
        """Espera navegación."""
        self.page.wait_for_load_state("networkidle", timeout=timeout)

    def apply(self) -> bool:
        """Método principal - override en subclases."""
        raise NotImplementedError


class LeverATS(BaseATS):
    """Auto-aplicación para Lever."""

    def apply(self) -> bool:
        page = self.page

        # 1. Navegar a la URL del job
        page.goto(self.job["url"], wait_until="networkidle")

        # 2. Click "Apply for this job" si hay landing page
        apply_selectors = [
            'a:has-text("Apply")',
            'button:has-text("Apply")',
            'a[data-qa="apply-button"]',
            'a[href*="/apply"]',
        ]
        for sel in apply_selectors:
            if self.safe_click(sel):
                self.wait_for_navigation()
                break

        # 3. Formulario de aplicación
        # Lever suele tener: nombre, email, teléfono, LinkedIn, GitHub, CV, preguntas
        self.fill_personal_info()

        # CV
        self.upload_cv()

        # Preguntas adicionales
        self.answer_common_questions()

        # Cover letter si hay campo
        cover_letter = self.profile.get("cover_letter", "")
        if cover_letter:
            self.safe_fill('textarea[name*="cover"], textarea[name*="letter"]', cover_letter)

        # 4. Submit
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit Application")',
            'button[type="submit"]:has-text("Apply")',
            'button[data-qa="submit-application"]',
        ]
        for sel in submit_selectors:
            if self.safe_click(sel):
                self.wait_for_navigation(30000)
                # Verificar éxito
                if page.query_selector('text="Application submitted", text="Thank you", .success, [data-qa="application-success"]'):
                    self.applied = True
                    return True
        return False


class GreenhouseATS(BaseATS):
    """Auto-aplicación para Greenhouse."""

    def apply(self) -> bool:
        page = self.page
        page.goto(self.job["url"], wait_until="networkidle")

        # Fix form for file upload: change to POST with multipart/form-data
        form = page.query_selector('form[action*="/jobs/"]')
        if form:
            page.evaluate('''form => {
                form.method = "POST";
                form.enctype = "multipart/form-data";
            }''', page.query_selector('form[action*="/jobs/"]'))

        # Greenhouse: detectar formulario
        self.fill_personal_info()
        self.upload_cv()
        self.answer_common_questions()

        # Cover letter
        cover = self.profile.get("cover_letter", "")
        if cover:
            self.safe_fill('textarea[name*="cover"], textarea[id*="cover"]', cover)

        # Click submit button instead of form.submit()
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit Application")',
            'button[type="submit"]',
            'input[type="submit"][value*="Submit"]',
        ]
        for sel in submit_selectors:
            if self.safe_click(sel):
                self.wait_for_navigation(30000)
                if page.query_selector('text="Thank you", text="Application received", .success-message'):
                    self.applied = True
                    return True
        return False


class AshbyATS(BaseATS):
    """Auto-aplicación para Ashby."""

    def apply(self) -> bool:
        page = self.page
        page.goto(self.job["url"], wait_until="networkidle")

        # Ashby suele tener multi-step form
        self.fill_personal_info()
        self.upload_cv()
        self.answer_common_questions()

        # Navegar steps
        for _ in range(5):  # max 5 steps
            next_selectors = [
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'button[type="submit"]',
            ]
            clicked = False
            for sel in next_selectors:
                if self.safe_click(sel):
                    self.wait_for_navigation()
                    clicked = True
                    break
            if not clicked:
                break

        # Submit final
        if self.safe_click('button:has-text("Submit"), button:has-text("Apply")'):
            self.wait_for_navigation(30000)
            if page.query_selector('text="Submitted", text="Thank you", .confirmation'):
                self.applied = True
                return True
        return False


def detect_ats(url: str) -> Optional[str]:
    """Detecta ATS por URL."""
    url = url.lower()
    if "lever.co" in url or "jobs.lever.co" in url:
        return "lever"
    if "greenhouse.io" in url or "boards.greenhouse.io" in url:
        return "greenhouse"
    if "ashbyhq.com" in url or "jobs.ashbyhq.com" in url:
        return "ashby"
    return None


def get_ats_handler(ats: str, page: Page, job: dict, profile: dict, cv_path: str) -> BaseATS:
    """Factory para handlers."""
    handlers = {
        "lever": LeverATS,
        "greenhouse": GreenhouseATS,
        "ashby": AshbyATS,
    }
    handler_class = handlers.get(ats)
    if not handler_class:
        raise ValueError(f"ATS no soportado: {ats}")
    return handler_class(page, job, profile, cv_path)


def auto_apply_job(job: dict, profile: dict, cv_path: str, headless: bool = True) -> Dict:
    """
    Auto-aplica a un job.
    Returns: {success: bool, ats: str, message: str}
    """
    if not os.path.exists(cv_path):
        return {"success": False, "error": f"CV no encontrado: {cv_path}"}

    ats = detect_ats(job["url"])
    if not ats:
        return {"success": False, "error": f"ATS no detectado para {job['url']}"}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            handler = get_ats_handler(ats, page, job, profile, cv_path)
            success = handler.apply()

            # Update DB
            conn = get_conn()
            conn.execute(
                "UPDATE jobs SET status='applied', applied_date=datetime('now') WHERE source=? AND external_id=?",
                (job["source"], job["external_id"]),
            )
            conn.commit()

            return {"success": success, "ats": ats, "message": "Applied" if success else "Failed to submit"}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            browser.close()


if __name__ == "__main__":
    # Test manual
    init_db()
    conn = get_conn()
    job = conn.execute("SELECT * FROM jobs WHERE match_score >= 80 AND status='new' LIMIT 1").fetchone()

    if job:
        job = dict(job)
        profile = {
            "first_name": "Oscar",
            "last_name": "DevOps",
            "email": "oscar@example.com",
            "phone": "+506 1234 5678",
            "linkedin": "https://linkedin.com/in/ozdevops",
            "github": "https://github.com/ozdevops",
            "portfolio": "https://services.o7team.us",
            "cover_letter": "Experienced DevOps Architect...",
        }
        result = auto_apply_job(job, profile, "/home/Helios/cv.pdf", headless=False)
        print(result)
    else:
        print("No hay jobs para aplicar")