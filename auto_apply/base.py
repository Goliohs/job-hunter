"""Base class para auto-aplicación a ATS."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class CandidateProfile:
    """Perfil del candidato para auto-rellenar formularios."""
    full_name: str
    email: str
    phone: str
    linkedin: str
    github: str
    portfolio: str
    location: str
    visa_status: str
    notice_period: str
    salary_expectation: str
    cv_path: str
    cover_letter_path: Optional[str] = None
    custom_fields: Dict[str, str] = None

    def __post_init__(self):
        if self.custom_fields is None:
            self.custom_fields = {}


class ATSBase(ABC):
    """Clase base para auto-aplicación a diferentes ATS."""

    def __init__(self, profile: CandidateProfile, headless: bool = True, semi_auto: bool = False):
        self.profile = profile
        self.headless = headless
        self.semi_auto = semi_auto
        self.browser = None
        self.context = None
        self.page = None

    @abstractmethod
    def apply(self, job_url: str) -> Dict[str, Any]:
        """Aplica a una oferta. Devuelve {success: bool, message: str, application_id: str}."""
        pass

    @abstractmethod
    def fill_personal_info(self) -> bool:
        """Rellena info personal (nombre, email, teléfono, etc.)."""
        pass

    @abstractmethod
    def upload_cv(self) -> bool:
        """Sube el CV."""
        pass

    @abstractmethod
    def upload_cover_letter(self) -> bool:
        """Sube la cover letter si existe."""
        pass

    @abstractmethod
    def answer_custom_questions(self) -> bool:
        """Responde preguntas personalizadas del ATS."""
        pass

    @abstractmethod
    def submit_application(self) -> bool:
        """Envía la aplicación final."""
        pass

    def setup_browser(self):
        """Inicializa Playwright browser."""
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-web-security",
                "--no-sandbox",
            ],
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        self.page = self.context.new_page()
        # Anti-detection
        self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

    def close_browser(self):
        """Cierra browser y playwright."""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if hasattr(self, 'playwright'):
            self.playwright.stop()

    def safe_click(self, selector: str, timeout: int = 5000) -> bool:
        """Click seguro con espera."""
        try:
            self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            self.page.click(selector)
            return True
        except Exception as e:
            print(f"[apply] Click failed on {selector}: {e}")
            return False

    def safe_fill(self, selector: str, value: str, timeout: int = 5000) -> bool:
        """Fill seguro con espera."""
        try:
            self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            self.page.fill(selector, value)
            return True
        except Exception as e:
            print(f"[apply] Fill failed on {selector}: {e}")
            return False

    def safe_select(self, selector: str, value: str, timeout: int = 5000) -> bool:
        """Select option seguro."""
        try:
            self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            self.page.select_option(selector, value=value)
            return True
        except Exception as e:
            print(f"[apply] Select failed on {selector}: {e}")
            return False

    def safe_upload(self, selector: str, file_path: str, timeout: int = 10000) -> bool:
        """Upload file seguro."""
        try:
            path = Path(file_path).resolve()
            if not path.exists():
                print(f"[apply] File not found: {path}")
                return False
            self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            self.page.set_input_files(selector, str(path))
            return True
        except Exception as e:
            print(f"[apply] Upload failed on {selector}: {e}")
            return False

    def wait_for_navigation(self, timeout: int = 30000):
        """Espera navegación."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass

    def verify_submission_success(self, timeout: int = 15000) -> Dict[str, Any]:
        """Verifica si una aplicación fue enviada exitosamente.

        Busca señales de éxito en este orden:
        1. URL cambio a /thanks, /success, /confirmation
        2. Texto de confirmación visible ("Thank you", "Your application has been received")
        3. Elementos de confirmación comunes

        Returns:
            {"success": bool, "application_id": str, "message": str}
        """
        import re

        # Dar tiempo a que la página cargue
        self.page.wait_for_timeout(2000)

        # 1. Check URL change
        current_url = self.page.url.lower()
        success_url_patterns = ["/thanks", "/success", "/confirmation", "thank-you", "applied"]
        for pattern in success_url_patterns:
            if pattern in current_url:
                # Intentar extraer application ID de la URL
                app_id_match = re.search(r'application[/=]?(\d+)', current_url)
                app_id = app_id_match.group(1) if app_id_match else ""
                return {
                    "success": True,
                    "application_id": app_id,
                    "message": f"Success detected via URL: {self.page.url}",
                }

        # 2. Check for success text in page
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

        # 3. Check for success-specific elements
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

        # 4. Check for CAPTCHA failure
        captcha_texts = ["captcha-failed", "unable to verify", "captcha response"]
        try:
            for text in captcha_texts:
                if text in page_text:
                    return {
                        "success": False,
                        "application_id": "",
                        "message": "CAPTCHA blocked - Greenhouse anti-bot protection active on this job",
                    }
        except Exception:
            pass

        # 5. Check for error messages (validation failed)
        error_texts = [
            "this field is required",
            "please fix the following errors",
            "there was a problem",
            "upload a resume",
            "file is required",
            "invalid email",
            "please enter",
        ]
        try:
            for text in error_texts:
                if text in page_text:
                    return {
                        "success": False,
                        "application_id": "",
                        "message": f"Validation error detected: '{text}'",
                    }
        except Exception:
            pass

        # 5. Check for error elements
        error_selectors = [
            ".error", ".field-error", ".form-error", ".alert-danger",
            '[data-qa="error-message"]', '[role="alert"]',
        ]
        for selector in error_selectors:
            try:
                els = self.page.query_selector_all(selector)
                for el in els:
                    if el.is_visible():
                        el_text = el.inner_text().strip().lower()
                        if el_text and not ("thank" in el_text or "success" in el_text):
                            return {
                                "success": False,
                                "application_id": "",
                                "message": f"Error element detected: '{el_text[:100]}'",
                            }
            except Exception:
                continue

        # 6. Ambiguous - could be loading or could have failed silently
        return {
            "success": False,
            "application_id": "",
            "message": "No success or error signal detected after submit",
        }

    def detect_multi_step_form(self) -> bool:
        """Detecta si el formulario es multi-página y necesita navegación."""
        step_indicators = [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Step 2")',
            '.step-indicator',
            '.progress-bar',
        ]
        for selector in step_indicators:
            try:
                el = self.page.query_selector(selector)
                if el and el.is_visible():
                    return True
            except Exception:
                continue
        return False

    def wait_for_human_submit(self, timeout: int = 600) -> Dict[str, Any]:
        """Modo semi-auto: espera que el humano resuelva CAPTCHA y haga click en Submit.

        Monitorea el estado de la página periódicamente:
        - Detecta cambio de URL (success/thanks pages)
        - Detecta texto de confirmación
        - Detecta errores de validación
        - Timeout tras N segundos

        Returns: resultado de verify_submission_success() o timeout
        """
        print("\n" + "=" * 60)
        print("  MODO SEMI-AUTO — La página está lista")
        print("  1. Resuelve el CAPTCHA si lo hay")
        print("  2. Revisa que los campos estén correctos")
        print("  3. Haz click en 'Submit application'")
        print(f"  Timeout: {timeout}s. La página quedará abierta.")
        print("=" * 60 + "\n")

        screenshot_path = "/tmp/semi_auto_filled_form.png"
        try:
            self.page.screenshot(path=screenshot_path, full_page=True)
            print(f"  Screenshot del form lleno: {screenshot_path}")
        except Exception:
            pass

        initial_url = self.page.url
        deadline_chunk = 2000  # ms entre checks
        elapsed = 0

        while elapsed < timeout * 1000:
            try:
                self.page.wait_for_timeout(deadline_chunk)
                elapsed += deadline_chunk

                # Detectar cambio de URL
                if self.page.url != initial_url:
                    print(f"[semi-auto] URL cambió: {self.page.url}")
                    self.page.wait_for_timeout(2000)
                    return self.verify_submission_success()

                # Detectar success text en DOM
                try:
                    body_text = self.page.inner_text("body", timeout=2000).lower()
                    success_markers = [
                        "thank you for applying",
                        "your application has been received",
                        "application submitted",
                        "application received",
                        "application complete",
                        "you have successfully applied",
                    ]
                    for marker in success_markers:
                        if marker in body_text:
                            print(f"[semi-auto] Success detected: '{marker}'")
                            return self.verify_submission_success()
                except Exception:
                    pass

                # Cada 30s, recordar al usuario
                if elapsed >= 30000 and (elapsed % 30000) < deadline_chunk:
                    print(f"[semi-auto] Esperando submit manual... ({elapsed//1000}s/{timeout}s)")

            except Exception as e:
                # La página pudo haberse cerrado (browser closed por humano)
                print(f"[semi-auto] Page/session error: {e}")
                return {
                    "success": False,
                    "application_id": "",
                    "message": f"Session ended: {e}",
                }

        print(f"[semi-auto] Timeout tras {timeout}s sin detectar submit")
        return {
            "success": False,
            "application_id": "",
            "message": f"Semi-auto timeout ({timeout}s) — sin señal de submit",
        }