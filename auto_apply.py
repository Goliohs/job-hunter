"""Auto-aplicación a ATS (Lever, Greenhouse, Ashby) con Playwright."""
import os
import sys
from pathlib import Path
from typing import Dict, Optional, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import get_conn, init_db
from generator import generate_application_package, load_base_cv, generate_application_pdfs


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


class BaseATS:
    """Clase base para handlers ATS."""

    def __init__(self, page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
        self.applied = False

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

    def fill_personal_info(self):
        """Llena info personal común."""
        p = self.profile
        self.safe_fill('input[name*="first"]', p.get("first_name", ""))
        self.safe_fill('input[name*="last"]', p.get("last_name", ""))
        self.safe_fill('input[type="email"], input[name*="email"]', p.get("email", ""))
        self.safe_fill('input[type="tel"], input[name*="phone"]', p.get("phone", ""))
        self.safe_fill('input[name*="linkedin"]', p.get("linkedin", ""))
        self.safe_fill('input[name*="github"]', p.get("github", ""))
        self.safe_fill('input[name*="portfolio"], input[name*="website"]', p.get("portfolio", ""))

    def upload_cv(self) -> bool:
        """Sube CV."""
        try:
            file_inputs = self.page.query_selector_all('input[type="file"]')
            for inp in file_inputs:
                if inp.is_visible():
                    inp.set_input_files(self.cv_path)
                    return True
        except Exception:
            pass
        return False

    def answer_common_questions(self):
        """Responde preguntas comunes (visa, remote, notice)."""
        page = self.page

        # Selects típicos
        selects = page.query_selector_all("select")
        for sel in selects:
            try:
                # Buscar label asociado
                label = ""
                parent = sel.query_selector("xpath=..")
                if parent:
                    label = parent.inner_text().lower()

                options = sel.query_selector_all("option")
                for opt in options:
                    text = opt.inner_text().lower()
                    val = opt.get_attribute("value")

                    # Visa sponsorship
                    if "visa" in label or "sponsor" in label:
                        if "no" in text or "not required" in text or "not need" in text:
                            sel.select_option(value=val)
                            break

                    # Remote preference
                    if "remote" in label or "location" in label:
                        if "remote" in text or "anywhere" in text or "worldwide" in text:
                            sel.select_option(value=val)
                            break

                    # Notice period
                    if "notice" in label or "availability" in label:
                        if "immediate" in text or "0" in text or "1 week" in text:
                            sel.select_option(value=val)
                            break
            except Exception:
                continue

    def apply(self) -> bool:
        """Override en subclases."""
        raise NotImplementedError


class LeverATS(BaseATS):
    """Handler para Lever."""

    def apply(self) -> bool:
        page = self.page

        # 1. Ir a URL del job
        page.goto(self.job["url"], wait_until="networkidle")

        # 2. Click "Apply" si hay landing
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

        # 3. Formulario
        self.fill_personal_info()
        self.upload_cv()
        self.answer_common_questions()

        # Cover letter
        cover = self.profile.get("cover_letter", "")
        if cover:
            self.safe_fill('textarea[name*="cover"], textarea[name*="letter"]', cover)

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
                if page.query_selector('text="Application submitted", text="Thank you", .success, [data-qa="application-success"]'):
                    self.applied = True
                    return True
        return False


class GreenhouseATS(BaseATS):
    """Handler para Greenhouse."""

    def apply(self) -> bool:
        page = self.page
        page.goto(self.job["url"], wait_until="networkidle")

        # Wait for form to load
        page.wait_for_selector('form[action*="/jobs/"]', timeout=10000)

        # Fill personal info fields using label-based xpath
        self.fill_greenhouse_personal_info()
        self.upload_cv()
        self.answer_common_questions()

        # Cover letter
        cover = self.profile.get("cover_letter", "")
        if cover:
            page.fill('//label[contains(text(), "Cover")]/following-sibling::textarea | //label[contains(text(), "Letter")]/following-sibling::textarea', cover)

        # Submit
        if self.safe_click('button:has-text("Submit application")'):
            self.wait_for_navigation(30000)
            if page.query_selector('text="Thank you", text="Application received", .success, [data-qa="application-success"], text="Application submitted"'):
                self.applied = True
                return True
        return False

    def fill_greenhouse_personal_info(self):
        """Fill Greenhouse-specific personal info fields."""
        p = self.profile
        
        # Basic fields
        self.safe_fill('#first_name', p.get("first_name", ""))
        self.safe_fill('#last_name', p.get("last_name", ""))
        self.safe_fill('#email', p.get("email", ""))
        self.safe_fill('#phone', p.get("phone", ""))
        
        # LinkedIn, Website, GitHub
        self.safe_fill('#question_51809697', p.get("linkedin", ""))
        self.safe_fill('#question_51809696', p.get("portfolio", ""))
        self.safe_fill('input[id*="github"]', p.get("github", ""))
        
        # Location/Country
        self.safe_fill('#question_51809699', p.get("location", "Remote Worldwide"))
        self.safe_fill('#country', p.get("location", "Remote Worldwide"))
        
        # Website field
        self.safe_fill('#question_51809696', p.get("portfolio", ""))
        
        # Cover letter field
        cover = self.profile.get("cover_letter", "")
        if cover:
            self.safe_fill('#cover_letter', cover)
            self.safe_fill('textarea[name="cover_letter"]', cover)
            self.safe_fill('textarea[id*="cover"]', cover)
        
        # Consent/agreement checkboxes
        self.safe_click('#question_51809700')  # Privacy policy consent
        
        # Answer select questions
        self.answer_greenhouse_selects()

    def answer_greenhouse_selects(self):
        """Answer Greenhouse select questions."""
        page = self.page
        
        selects = page.query_selector_all('select')
        for sel in selects:
            try:
                label = sel.evaluate('el => el.labels?.[0]?.textContent || ""').lower()
                
                options = sel.query_selector_all('option')
                for opt in options:
                    text = opt.inner_text().lower()
                    val = opt.get_attribute('value')
                    
                    # Visa sponsorship
                    if 'visa' in label or 'sponsor' in label:
                        if 'no' in text or 'not required' in text:
                            sel.select_option(value=val)
                            break
                    
                    # Remote preference
                    if 'remote' in label or 'location' in label or 'work location' in label:
                        if 'remote' in text or 'anywhere' in text or 'worldwide' in text:
                            sel.select_option(value=val)
                            break
                    
                    # Notice period
                    if 'notice' in label or 'availability' in label:
                        if 'immediate' in text or '0' in text or '1 week' in text:
                            sel.select_option(value=val)
                            break
                    
                    # Country
                    if 'country' in label and 'currently' in label:
                        if 'remote' in text or 'worldwide' in text or 'anywhere' in text:
                            sel.select_option(value=val)
                            break
                        elif 'costa rica' in text.lower():
                            sel.select_option(value=val)
                            break
                    
                    # Gender
                    if 'gender' in label:
                        if 'prefer not' in text:
                            sel.select_option(value=val)
                            break
                    
                    # Ethnicity/race
                    if 'ethnicity' in label or 'race' in label or 'hispanic' in label:
                        if 'prefer not' in text:
                            sel.select_option(value=val)
                            break
                            
            except Exception:
                continue
EOF


class AshbyATS(BaseATS):
    """Handler para Ashby."""

    def apply(self) -> bool:
        page = self.page
        page.goto(self.job["url"], wait_until="networkidle")

        # Ashby: multi-step form
        for _ in range(5):
            self.fill_personal_info()
            self.upload_cv()
            self.answer_common_questions()

            # Next step
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


HANDLERS = {
    "lever": LeverATS,
    "greenhouse": GreenhouseATS,
    "ashby": AshbyATS,
}


def auto_apply_job(job: dict, profile: dict, cv_path: str, headless: bool = True) -> Dict[str, Any]:
    """Auto-aplica a un job. Returns dict con resultado."""
    if not os.path.exists(cv_path):
        return {"success": False, "error": f"CV no encontrado: {cv_path}"}

    ats = detect_ats(job["url"])
    if not ats:
        return {"success": False, "error": f"ATS no detectado para {job['url']}"}

    handler_class = HANDLERS.get(ats)
    if not handler_class:
        return {"success": False, "error": f"ATS no soportado: {ats}"}

    # Generate personalized application package
    print(f"  📝 Generando aplicación personalizada para {job['company']}...")
    package = generate_application_package(job, profile, cv_path)
    
    # Generate PDFs
    print(f"  📄 Generando PDFs (cover letter + CV adaptado)...")
    pdf_files = generate_application_pdfs(job, package, profile)
    
    # Use generated CV PDF if available, else fallback to original
    effective_cv_path = pdf_files.get("cv_pdf", cv_path)
    personalized_cover = package.get("cover_letter", profile.get("cover_letter", ""))

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        try:
            handler = handler_class(page, job, profile, effective_cv_path)
            # Override cover letter with personalized one
            handler.profile["cover_letter"] = personalized_cover
            success = handler.apply()

            # Update DB
            conn = get_conn()
            conn.execute(
                "UPDATE jobs SET status='applied', applied_date=datetime('now') WHERE source=? AND external_id=?",
                (job["source"], job["external_id"]),
            )
            conn.commit()

            return {"success": success, "ats": ats, "message": "Applied" if success else "Failed to submit", "pdfs_generated": list(pdf_files.keys())}

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