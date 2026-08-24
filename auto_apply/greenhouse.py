"""Auto-aplicacion para Greenhouse ATS."""
from typing import Dict, Any
from playwright.sync_api import Page


class GreenhouseATS:
    """Aplicacion automatica para Greenhouse."""

    def __init__(self, page: Page, job: dict, profile: dict, cv_path: str, semi_auto: bool = False):
        self.page = page
        self.job = job
        self.profile = profile
        self.cv_path = cv_path
        self.cover_letter_path = profile.get("cover_letter_path", "")
        self.semi_auto = semi_auto

    def apply(self, job_url: str = None) -> Dict[str, Any]:
        try:
            print(f"[greenhouse] Navegando a {self.job['url']}")
            self.page.goto(self.job["url"], wait_until="networkidle", timeout=60000)
            self.page.wait_for_load_state("networkidle")

            # Fix form for file upload: change to POST with multipart/form-data
            form = self.page.query_selector('form[action*="/jobs/"]')
            if form:
                self.page.evaluate('''form => {
                    form.method = "POST";
                    form.enctype = "multipart/form-data";
                }''', form)

            if "greenhouse.io" not in self.page.url and "grnh.se" not in self.page.url:
                return {"success": False, "message": "No es pagina de Greenhouse"}

            self.page.screenshot(path="/tmp/greenhouse_landing.png")

            form_el = self.page.query_selector(
                "input#first_name, input#email, input#resume, textarea"
            )
            form_already_visible = form_el and form_el.is_visible()

            if not form_already_visible:
                print("[greenhouse] Form not visible, looking for Apply button...")
                apply_btn = self.page.query_selector(
                    'button:has-text("Apply"), a:has-text("Apply")'
                )
                if apply_btn and apply_btn.is_visible():
                    print(f"[greenhouse] Clicking: '{apply_btn.inner_text().strip()}'")
                    apply_btn.click()
                    self.page.wait_for_load_state("networkidle")
                    self.page.wait_for_timeout(3000)

            print("[greenhouse] Filling personal info...")
            fill_result = self.fill_personal_info()
            if isinstance(fill_result, dict) and not fill_result.get("success", True):
                return fill_result
            if fill_result is False:
                return {"success": False, "message": "Fallo info personal"}

            print("[greenhouse] Uploading CV...")
            if not self.upload_cv():
                return {"success": False, "message": "Fallo subida CV"}

            if self.cover_letter_path:
                print("[greenhouse] Uploading cover letter...")
                self.upload_cover_letter()

            print("[greenhouse] Answering custom questions...")
            self.answer_custom_questions()

            result = self.submit_application()
            return result

        except Exception as e:
            return {"success": False, "message": f"Error Greenhouse: {e}"}

    def fill_personal_info(self):
        p = self.profile
        first = p.get("first_name", "") if p.get("first_name") else ""
        last = p.get("last_name", "") if p.get("last_name") else ""

        for inp_id, value in {
            "first_name": first, "last_name": last,
            "email": p.get("email", ""), "phone": p.get("phone", ""),
        }.items():
            if not value:
                continue
            inp = self.page.query_selector(f"input#{inp_id}")
            if inp and inp.is_visible():
                inp.fill(value)

        country_inp = self.page.query_selector("input#country")
        if country_inp and country_inp.is_visible():
            self._select_combobox(country_inp, search_text=p.get("location", "").split(",")[0].strip())

        for inp_id, value in [
            ("question_17865759004", p.get("linkedin", "")),
            ("question_17865760004", p.get("github", "")),
        ]:
            if not value:
                continue
            inp = self.page.query_selector(f"#{inp_id}")
            if inp and inp.is_visible():
                inp.fill(value)

        result = self._keyboard_fill_questions()
        if isinstance(result, dict) and not result.get("success", True):
            return result
        return True

    def _keyboard_fill_questions(self):
        p = self.profile
        broken_fields = []
        
        # Dynamically find and fill required question fields
        # Look for textareas and inputs with aria-required=true
        required_inputs = self.page.query_selector_all('input[aria-required="true"], textarea[aria-required="true"]')
        for inp in required_inputs:
            id_ = inp.get_attribute('id')
            if not id_:
                continue
            
            # Find associated label to understand what this field is
            label_text = ""
            label = self.page.query_selector(f'label[for="{id_}"]')
            if label:
                label_text = label.inner_text().lower()
            
            # Check if this is a combobox (role=combobox) - if so, handle separately
            role = inp.get_attribute('role')
            if role == 'combobox':
                # Check if combobox options are valid for this field
                inp.click()
                self.page.wait_for_timeout(500)
                opts = self.page.query_selector_all('[role="option"]')
                first_options = [opt.inner_text().lower() for opt in opts[:5]]
                self.page.keyboard.press('Escape')
                self.page.wait_for_timeout(200)
                
                # If options look like country codes (+93, +1, etc.), this is a broken field
                is_country_dropdown = any('+' in opt and any(c.isdigit() for c in opt) for opt in first_options)
                if is_country_dropdown and not ('country' in label_text or 'phone' in label_text):
                    broken_fields.append(f"{id_}: {label_text[:50]} (country dropdown)")
                    continue
                
                value = self._get_combo_answer_for_label(label_text, p)
                if value:
                    print(f"[greenhouse] Filling required combobox {id_} ({label_text[:50]}): {value}")
                    self._select_combobox(inp, value)
                continue
            
            # Fill based on label content
            value = self._get_answer_for_label(label_text, p)
            if value:
                print(f"[greenhouse] Filling required field {id_} ({label_text[:50]}): {value[:50]}")
                inp.fill(value)

        # Fill other required comboboxes (aria-required=true, not already handled)
        required_combos = self.page.query_selector_all('input[aria-required="true"][role="combobox"]')
        for combo in required_combos:
            id_ = combo.get_attribute('id')
            if not id_:
                continue
            
            # Skip if already processed above
            if any(bf.startswith(id_ + ":") for bf in broken_fields):
                continue
            
            label_text = ""
            label = self.page.query_selector(f'label[for="{id_}"]')
            if label:
                label_text = label.inner_text().lower()
            
            # Check if combobox options are valid
            combo.click()
            self.page.wait_for_timeout(500)
            opts = self.page.query_selector_all('[role="option"]')
            first_options = [opt.inner_text().lower() for opt in opts[:5]]
            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(200)
            
            is_country_dropdown = any('+' in opt and any(c.isdigit() for c in opt) for opt in first_options)
            if is_country_dropdown and not ('country' in label_text or 'phone' in label_text):
                broken_fields.append(f"{id_}: {label_text[:50]} (country dropdown)")
                continue
            
            value = self._get_combo_answer_for_label(label_text, p)
            if value:
                print(f"[greenhouse] Filling required combobox {id_} ({label_text[:50]}): {value}")
                self._select_combobox(combo, value)

        # Also fill EEO comboboxes (optional but good to complete)
        eeos = [
            ("#gender", "Male"),
            ("#hispanic_ethnicity", "No"),
            ("#veteran_status", "I am not a protected veteran"),
            ("#disability_status", "No, I don't have a disability"),
        ]
        for combo_id, value in eeos:
            el = self.page.query_selector(combo_id)
            if el and el.is_visible():
                self._select_combobox(el, value)

        # If there are broken required fields, fail fast in auto mode, but continue in semi-auto
        if broken_fields:
            msg = "Form has broken required fields (country dropdown on non-country fields): " + "; ".join(broken_fields)
            print(f"[greenhouse] ERROR: {msg}")
            if self.semi_auto:
                print("[greenhouse] SEMI-AUTO: Continuing despite broken fields - human will fill them")
            else:
                return {"success": False, "message": msg}

    def _get_answer_for_label(self, label_text: str, profile: dict) -> str:
        """Determine answer based on field label."""
        label_text = label_text.lower()
        
        if "linkedin" in label_text:
            return profile.get("linkedin", "")
        elif "github" in label_text:
            return profile.get("github", "")
        elif "portfolio" in label_text or "website" in label_text or "personal site" in label_text:
            return profile.get("portfolio", "")
        elif "location" in label_text or "current location" in label_text:
            return profile.get("location", "Costa Rica")
        elif "postgres" in label_text and ("year" in label_text or "experience" in label_text):
            return "10+ years managing Postgres clusters, extensions, replication, and performance tuning"
        elif "sponsor" in label_text or "visa" in label_text or "work authoriz" in label_text:
            return "No"
        elif "ai" in label_text and "consent" in label_text:
            return "Yes"
        elif "year" in label_text and "experience" in label_text:
            return "10+ years building AI/ML infrastructure, private AI platform with Ollama/vLLM on GPU nodes"
        elif "notice" in label_text or "availab" in label_text:
            return profile.get("notice_period", "Immediate")
        elif "salary" in label_text or "compensation" in label_text:
            return profile.get("salary_expectation", "Negotiable")
        
        return ""

    def _get_combo_answer_for_label(self, label_text: str, profile: dict) -> str:
        """Determine combobox answer based on field label."""
        label_text = label_text.lower()
        
        if "country" in label_text:
            return profile.get("location", "Costa Rica").split(",")[0].strip()
        elif "gender" in label_text:
            return "Male"
        elif "hispanic" in label_text or "latino" in label_text:
            return "No"
        elif "veteran" in label_text:
            return "I am not a protected veteran"
        elif "disabilit" in label_text:
            return "No, I don't have a disability"
        elif "sponsor" in label_text or "visa" in label_text:
            return "No"
        
        return ""

    def _select_combobox(self, element, search_text: str):
        """Handle Greenhouse combobox (custom dropdown)."""
        try:
            element.click()
            self.page.wait_for_timeout(500)
            self.page.keyboard.type(search_text)
            self.page.wait_for_timeout(500)
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(300)
        except Exception as e:
            print(f"[greenhouse] Combobox failed: {e}")

    def _select_dropdown(self, selector: str, search_text: str):
        """Handle native select dropdowns."""
        try:
            self.page.click(selector)
            self.page.wait_for_timeout(300)
            self.page.keyboard.type(search_text)
            self.page.wait_for_timeout(200)
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(200)
        except Exception as e:
            print(f"[greenhouse] Dropdown failed on {selector}: {e}")

    def upload_cv(self) -> bool:
        if not self.cv_path:
            return False
        try:
            import os
            if not os.path.exists(self.cv_path):
                print(f"[greenhouse] CV not found: {self.cv_path}")
                return False
            inp = self.page.query_selector('input#resume, input[type="file"][name="resume"]')
            if inp and inp.is_visible():
                inp.set_input_files(self.cv_path)
                self.page.wait_for_timeout(3000)
                return True
        except Exception as e:
            print(f"[greenhouse] Upload failed: {e}")
        return False

    def upload_cover_letter(self) -> bool:
        if not self.cover_letter_path:
            return True
        try:
            inp = self.page.query_selector('input[name="cover_letter"], input[type="file"][name*="cover"]')
            if inp and inp.is_visible():
                inp.set_input_files(self.cover_letter_path)
                self.page.wait_for_timeout(2000)
                return True
        except Exception as e:
            print(f"[greenhouse] Cover letter upload failed: {e}")
        return False

    def answer_custom_questions(self) -> bool:
        self._keyboard_fill_questions()
        return True

    def submit_application(self) -> Dict[str, Any]:
        # Try clicking submit button first
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit Application")',
            'button[type="submit"]',
            'input[type="submit"][value*="Submit"]',
        ]
        for sel in submit_selectors:
            if self._safe_click(sel):
                print(f"[greenhouse] Clicked submit: {sel}")
                self.page.wait_for_timeout(5000)
                self.page.wait_for_load_state("networkidle")
                
                # Check for validation errors
                error_result = self._check_validation_errors()
                if error_result:
                    print(f"[greenhouse] Validation error: {error_result['message']}")
                    # Don't return yet, try form.submit() fallback
                
                result = self._verify_submission_success()
                if result.get("success"):
                    return result

        # Fallback: use form.submit() via evaluate
        print("[greenhouse] Trying form.submit() via evaluate...")
        try:
            form = self.page.query_selector('form[action*="/jobs/"]')
            if form:
                self.page.evaluate('''form => {
                    form.method = "POST";
                    form.enctype = "multipart/form-data";
                    form.submit();
                }''', form)
                self.page.wait_for_timeout(5000)
                self.page.wait_for_load_state("networkidle")
                result = self._verify_submission_success()
                if result.get("success"):
                    return result
        except Exception as e:
            print(f"[greenhouse] form.submit() failed: {e}")

        return {"success": False, "message": "No submit button found or form submit failed"}

    def _check_validation_errors(self) -> Dict[str, Any]:
        """Check for validation errors on the page."""
        error_selectors = [
            ".error", ".field-error", ".form-error", ".alert-danger",
            '[data-qa="error-message"]', '[role="alert"]',
            '.validation-error', '.error-message', '.field-error-message',
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
                                "message": f"Validation error: {el_text[:200]}",
                            }
            except Exception:
                continue
        return None

    def _safe_click(self, selector: str, timeout: int = 5000) -> bool:
        try:
            el = self.page.wait_for_selector(selector, state="visible", timeout=timeout)
            if el:
                el.click()
                return True
        except Exception as e:
            print(f"[greenhouse] Click failed on {selector}: {e}")
        return False

    def _verify_submission_success(self) -> Dict[str, Any]:
        import re
        self.page.wait_for_timeout(5000)

        print(f"[greenhouse] Checking submission result, current URL: {self.page.url}")

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

        # Check for CAPTCHA
        captcha_indicators = [
            "captcha",
            "recaptcha",
            "hcaptcha",
            "verify you are human",
            "please verify",
        ]
        try:
            page_text = self.page.inner_text("body", timeout=2000).lower()
            for indicator in captcha_indicators:
                if indicator in page_text:
                    return {
                        "success": False,
                        "application_id": "",
                        "message": f"CAPTCHA detected: {indicator}",
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

        # Check for error messages
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
                                "message": f"Error: {el_text[:200]}",
                            }
            except Exception:
                continue

        self.page.screenshot(path="/tmp/greenhouse_after_submit.png")
        return {
            "success": False,
            "application_id": "",
            "message": "No success signal detected after submit",
        }