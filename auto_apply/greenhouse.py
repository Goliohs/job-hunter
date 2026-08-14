"""Auto-aplicacion para Greenhouse ATS."""
from auto_apply.base import ATSBase, CandidateProfile
from typing import Dict, Any


class GreenhouseATS(ATSBase):
    """Aplicacion automatica para Greenhouse."""

    MAX_STEPS = 10

    def apply(self, job_url: str) -> Dict[str, Any]:
        self.setup_browser()
        try:
            print(f"[greenhouse] Navegando a {job_url}")
            self.page.goto(job_url, wait_until="networkidle", timeout=60000)
            self.wait_for_navigation()

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
                    self.wait_for_navigation()
                    self.page.wait_for_timeout(3000)
                    self.page.screenshot(path="/tmp/greenhouse_after_click.png")

            if not self.fill_personal_info():
                return {"success": False, "message": "Fallo info personal"}

            if not self.upload_cv():
                return {"success": False, "message": "Fallo subida CV"}

            if self.profile.cover_letter_path:
                self.upload_cover_letter()

            self.answer_custom_questions()

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
            return {"success": False, "message": f"Error Greenhouse: {e}"}
        finally:
            self.close_browser()

    def fill_personal_info(self) -> bool:
        p = self.profile
        first = p.full_name.split()[0] if p.full_name else ""
        last = " ".join(p.full_name.split()[1:]) if len(p.full_name.split()) > 1 else ""

        for inp_id, value in {
            "first_name": first, "last_name": last,
            "email": p.email, "phone": p.phone,
        }.items():
            if not value:
                continue
            inp = self.page.query_selector(f"input#{inp_id}")
            if inp and inp.is_visible():
                inp.fill(value)

        country_inp = self.page.query_selector("input#country")
        if country_inp and country_inp.is_visible():
            self._select_dropdown(country_inp, search_text=self.profile.location.split(",")[0].strip())

        for inp_id, value in [
            ("question_17865759004", p.linkedin),
            ("question_17865760004", p.github),
        ]:
            if not value:
                continue
            inp = self.page.query_selector(f"#{inp_id}")
            if inp and inp.is_visible():
                inp.fill(value)

        self._keyboard_fill_questions()

        return True

    def _keyboard_fill_questions(self):
        """Fill known question fields directly by ID."""
        # Ordered list of (id, label_keyword, action)
        # action: "type:VALUE" or "arrow:N"
        fields = [
            ("question_17865761004", "postgres|years", "type:5"),
            ("question_17865762004", "location", f"type:{self.profile.location.split(',')[0].strip()}"),
            ("question_17865763004", "sponsor", "arrow:1"),
            ("question_17865764004", "consent|ai", "arrow:2"),
        ]

        for inp_id, keywords, action in fields:
            el = self.page.query_selector(f"#{inp_id}")
            if not el:
                continue

            role = el.get_attribute("role") or ""
            label = self.page.query_selector(f"label[for='{inp_id}']")
            label_text = label.inner_text().strip().lower() if label else ""

            # Only fill if label matches expected keywords
            if not any(k in label_text for k in keywords.split("|")):
                continue

            if action.startswith("type:"):
                val = action.split(":", 1)[1]
                if role == "combobox":
                    self._select_dropdown(el, search_text=val)
                else:
                    el.fill(val)
            elif action.startswith("arrow:"):
                arrows = int(action.split(":", 1)[1])
                self._select_dropdown(el, arrow_presses=arrows)

    def _select_dropdown(self, inp, search_text=None, arrow_presses=0):
        """Select from a Greenhouse React Select dropdown."""
        try:
            inp.click()
            self.page.wait_for_timeout(500)

            if search_text:
                inp.type(search_text, delay=50)
                self.page.wait_for_timeout(1200)
                options = self.page.query_selector_all("[role='option']")
                for opt in options:
                    try:
                        if opt.is_visible():
                            opt.click()
                            self.page.wait_for_timeout(500)
                            self.page.keyboard.press("Tab")
                            self.page.wait_for_timeout(200)
                            return
                    except Exception:
                        continue
            else:
                self.page.wait_for_timeout(600)
                for _ in range(arrow_presses):
                    self.page.keyboard.press("ArrowDown")
                    self.page.wait_for_timeout(200)
                self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(500)
                self.page.keyboard.press("Tab")
                self.page.wait_for_timeout(200)
        except Exception:
            pass

    def upload_cv(self) -> bool:
        selectors = [
            "input#resume", "input[name='resume']",
            "input[type='file'][accept*='pdf']",
            "input[data-qa='resume-upload']",
            "input[type='file']",
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
            "input#cover_letter",
            "input[name='cover_letter']",
            "input[name='cover_letter_file']",
        ]
        for sel in selectors:
            if self.safe_upload(sel, self.profile.cover_letter_path):
                self.page.wait_for_timeout(2000)
                return True
        return False

    def answer_custom_questions(self) -> bool:
        step = 0
        while step < self.MAX_STEPS:
            step += 1
            print(f"[greenhouse] Navegando paso {step}...")
            self._skip_demographic()
            submit_btn = self.page.query_selector('button:has-text("Submit")')
            if submit_btn and submit_btn.is_visible():
                break
            self._fill_remaining_questions()
            if not self._click_continue():
                break
            self.wait_for_navigation()
            self.page.wait_for_timeout(1000)
        return True

    def _fill_remaining_questions(self):
        for label in self.page.query_selector_all("label"):
            try:
                label_text = label.inner_text().strip().lower()
                for_attr = label.get_attribute("for")
                if not for_attr:
                    continue
                inp = self.page.query_selector(f"#{for_attr}")
                if not inp or not inp.is_visible():
                    continue
                val = inp.input_value() or ""
                if val:
                    continue
                if "visa" in label_text or "work author" in label_text:
                    self._fill_input(inp, self.profile.visa_status)
                elif "notice" in label_text or "availability" in label_text:
                    self._fill_input(inp, self.profile.notice_period)
                elif "salary" in label_text or "compensation" in label_text:
                    self._fill_input(inp, self.profile.salary_expectation)
                elif "cover letter" in label_text:
                    self._fill_input(inp, self.profile.cover_letter_path or "")
                elif "website" in label_text or "portfolio" in label_text:
                    self._fill_input(inp, self.profile.portfolio)
            except Exception:
                continue

    def _fill_input(self, inp, value):
        if not value:
            return
        try:
            tag = inp.evaluate("el => el.tagName").lower()
            if tag == "select":
                inp.select_option(label=value)
            else:
                inp.fill(value)
        except Exception:
            pass

    def _skip_demographic(self):
        for sel in [".demographic-question", '[data-qa="demographic-question"]', ".eeoc-question"]:
            try:
                for el in self.page.query_selector_all(sel):
                    decline = el.query_selector(
                        "label:has-text(\"don't wish\"), label:has-text('prefer not'), "
                        "label:has-text('decline'), label:has-text(\"I don't\"), "
                        "label:has-text('skip')"
                    )
                    if decline:
                        decline.click()
            except Exception:
                pass

    def _click_continue(self) -> bool:
        for sel in [
            'button:has-text("Continue")', 'button:has-text("Next")',
            'button[type="submit"]:has-text("Continue")',
            'a:has-text("Continue")', 'a:has-text("Next")',
        ]:
            if self.safe_click(sel):
                self.wait_for_navigation()
                return True
        return False

    def submit_application(self) -> Dict[str, Any]:
        # Modo semi-auto: NO hacer click en submit, esperar al humano
        if self.semi_auto:
            print("[greenhouse] SEMI-AUTO: No se hará submit. Esperando humano...")
            return self.wait_for_human_submit(timeout=600)

        # Setup network interception for CAPTCHA detection
        captcha_detected = []
        def check_response(response):
            if response.status == 428:
                captcha_detected.append(response.text()[:200])
        self.page.on("response", check_response)

        for sel in [
            'button:has-text("Submit application")',
            'button:has-text("Submit Application")',
            'button:has-text("Submit")',
            'button[type="submit"]:has-text("Submit")',
            "input[type='submit']",
            "button.submit-button",
        ]:
            if self.safe_click(sel):
                print(f"[greenhouse] Clicked submit button: {sel}")
                break
        else:
            print("[greenhouse] No submit button found")

        self.page.wait_for_timeout(3000)
        self.wait_for_navigation()

        result = self.verify_submission_success()
        if not result["success"] and captcha_detected:
            result["message"] = "CAPTCHA blocked - Greenhouse anti-bot protection"
        if not result["success"]:
            self.page.screenshot(path="/tmp/greenhouse_submit_result.png")
        return result