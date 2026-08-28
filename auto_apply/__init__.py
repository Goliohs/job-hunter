"""Auto-aplicación a ATS (Lever, Greenhouse, Ashby) con Playwright."""
import os
import sys
from pathlib import Path
from typing import Dict, Optional
from playwright.sync_api import sync_playwright, Browser, Page, Playwright

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import get_conn, init_db
from auto_apply.lever import LeverATS
from auto_apply.greenhouse import GreenhouseATS
from auto_apply.ashby import AshbyATS
from auto_apply.base import ATSBase


def detect_ats(url: str) -> Optional[str]:
    """Detecta ATS por URL."""
    url = url.lower()
    if "lever.co" in url or "jobs.lever.co" in url:
        return "lever"
    if "greenhouse.io" in url or "boards.greenhouse.io" in url or "job-boards.greenhouse.io" in url:
        return "greenhouse"
    if "ashbyhq.com" in url or "jobs.ashbyhq.com" in url:
        return "ashby"
    if "workable.com" in url:
        return "workable"
    if "recruitee.com" in url:
        return "recruitee"
    if "teamtailor.com" in url:
        return "teamtailor"
    if "smartrecruiters.com" in url:
        return "smartrecruiters"
    if "icims.com" in url:
        return "icims"
    if "taleo.net" in url:
        return "taleo"
    if "workday.com" in url or "myworkdayjobs.com" in url:
        return "workday"
    if "jobvite.com" in url:
        return "jobvite"
    if "bamboohr.com" in url:
        return "bamboohr"
    if "comeet.com" in url:
        return "comeet"
    if "cisco.com" in url and "/jobs/" in url:
        return "cisco"
    return None


def get_ats_handler(ats: str, page: Page, job: dict, profile: dict, cv_path: str, semi_auto: bool = False):
    """Factory para handlers."""
    handlers = {
        "lever": LeverATS,
        "greenhouse": GreenhouseATS,
        "ashby": AshbyATS,
        "workable": WorkableATS,
        "recruitee": RecruiteeATS,
        "teamtailor": TeamtailorATS,
        "smartrecruiters": SmartRecruitersATS,
        "icims": ICIMSATS,
        "taleo": TaleoATS,
        "workday": WorkdayATS,
        "jobvite": JobviteATS,
        "bamboohr": BambooHRATS,
        "comeet": ComeetATS,
        "cisco": CiscoATS,
    }
    handler_class = handlers.get(ats)
    if not handler_class:
        raise ValueError(f"ATS no soportado: {ats}")

    # Solo pasar semi_auto si el handler lo acepta (stubs sin implementar no lo tienen)
    import inspect
    params = inspect.signature(handler_class.__init__).parameters
    if "semi_auto" in params:
        return handler_class(page, job, profile, cv_path, semi_auto=semi_auto)
    return handler_class(page, job, profile, cv_path)


def auto_apply_job(job: dict, profile: dict, cv_path: str, headless: bool = True, semi_auto: bool = False) -> Dict:
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
            handler = get_ats_handler(ats, page, job, profile, cv_path, semi_auto=semi_auto)
            result = handler.apply()

            # Handle both bool and dict returns
            if isinstance(result, dict):
                success = result.get("success", False)
                message = result.get("message", "Applied" if success else "Failed to submit")
            else:
                success = bool(result)
                message = "Applied" if success else "Failed to submit"

            # Update DB on success
            if success:
                conn = get_conn()
                conn.execute(
                    "UPDATE jobs SET status='applied', applied_date=datetime('now') WHERE source=? AND external_id=?",
                    (job["source"], job["external_id"]),
                )
                conn.commit()

            return {"success": success, "ats": ats, "message": message}

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
            "first_name": "YourName",
            "last_name": "DevOps",
            "email": "yourname@example.com",
            "phone": "+000 1234 5678",
            "linkedin": "https://linkedin.com/in/tuusuario",
            "github": "https://github.com/tuusuario",
            "portfolio": "https://your-portfolio.example.com",
            "cover_letter": "Experienced DevOps Architect...",
        }
        result = auto_apply_job(job, profile, "/home/youruser/cv.pdf", headless=False)
        print(result)
    else:
        print("No hay jobs para aplicar")


# Additional ATS handlers (minimal implementations)
class WorkableATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Workable ATS not yet implemented"}

class RecruiteeATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Recruitee ATS not yet implemented"}

class TeamtailorATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Teamtailor ATS not yet implemented"}

class SmartRecruitersATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "SmartRecruiters ATS not yet implemented"}

class ICIMSATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "iCIMS ATS not yet implemented"}

class TaleoATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Taleo ATS not yet implemented"}

class WorkdayATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Workday ATS not yet implemented"}

class JobviteATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Jobvite ATS not yet implemented"}

class BambooHRATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "BambooHR ATS not yet implemented"}

class ComeetATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Comeet ATS not yet implemented"}

class CiscoATS:
    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
    
    def apply(self) -> dict:
        return {"success": False, "message": "Cisco ATS not yet implemented"}