"""
Filler específico para Greenhouse ATS.

Basado en análisis real de formularios Greenhouse:
- Detecta campos required por aria-required
- Maneja comboboxes (React select) vs dropdowns nativos
- Detecta campos rotos (country dropdown en campos no-country)
- Llenado inteligente por label
"""
from typing import Any
from playwright.async_api import Page
from .fillers import ATSBaseFiller, FillResult, register_filler
import logging
import re
from datetime import datetime, timedelta, timezone

from pathlib import Path
logger = logging.getLogger(__name__)


@register_filler("greenhouse")
@register_filler("greenhouse_career")
class GreenhouseFiller(ATSBaseFiller):
    """Filler especializado para Greenhouse."""

    async def analyze(self) -> dict:
        """Analiza estructura del formulario Greenhouse."""
        # Fix form para file upload
        form = await self.page.query_selector('form[action*="/jobs/"]')
        if form:
            await self.page.evaluate('''form => {
                form.method = "POST";
                form.enctype = "multipart/form-data";
            }''', form)

        if "greenhouse.io" not in self.page.url and "grnh.se" not in self.page.url:
            return {"on_landing": True, "required_fields": [], "broken_fields": [], "ats": "greenhouse"}

        self.page.screenshot(path="/tmp/greenhouse_landing.png")

        form_el = await self.page.query_selector(
            "input#first_name, input#email, input#resume, textarea"
        )
        form_already_visible = form_el and await form_el.is_visible()

        if not form_already_visible:
            print("[greenhouse] Form not visible, looking for Apply button...")
            apply_btn = await self.page.query_selector(
                'button:has-text("Apply"), a:has-text("Apply")'
            )
            if apply_btn and await apply_btn.is_visible():
                print(f"[greenhouse] Clicking: '{await apply_btn.inner_text().strip()}'")
                await apply_btn.click()
                await self.page.wait_for_load_state("networkidle")
                await self.page.wait_for_timeout(2000)

        required_inputs = await self.page.query_selector_all('[aria-required="true"]')
        required_fields = []
        broken_fields = []

        for inp in required_inputs:
            field_id = await inp.get_attribute("id")
            if not field_id:
                continue

            role = await inp.get_attribute("role")
            label = await self._get_label_text(field_id)

            # Check if combobox options look like country dropdown
            if role == "combobox":
                await inp.click()
                await self.page.wait_for_timeout(300)
                opts = await self.page.query_selector_all('[role="option"]')
                first_opts = [await opt.inner_text() for opt in opts[:5]]
                await inp.press("Escape")
                await self.page.wait_for_timeout(200)

                is_country_dropdown = any(
                    '+' in opt and any(c.isdigit() for c in opt) for opt in first_opts
                )
                # Only mark as broken if it's a country field but has wrong options
                # Or if it's a non-country field with country-like options
                is_country_field = "country" in label.lower() or "phone" in label.lower()
                if is_country_dropdown and not is_country_field:
                    broken_fields.append({
                        "id": field_id,
                        "label": label[:50],
                        "sample_options": first_opts,
                    })

            required_fields.append({
                "id": field_id,
                "label": label,
                "type": inp.get_attribute("type") or "text",
                "role": role,
            })

        return {
            "on_landing": not form_already_visible,
            "required_fields": required_fields,
            "broken_fields": broken_fields,
            "ats": "greenhouse",
        }

    def _is_country_field(self, label: str) -> bool:
        """Verifica si el campo es legítimamente de país."""
        label_lower = label.lower()
        return any(kw in label_lower for kw in ["country", "país", "phone", "teléfono"])

    async def _get_label_text(self, field_id: str) -> str:
        """Obtiene texto del label asociado."""
        if not field_id:
            return ""
        label_el = await self.page.query_selector(f'label[for="{field_id}"]')
        if label_el:
            return (await label_el.inner_text()).strip()
        return ""

    async def navigate(self) -> bool:
        """Navega al formulario, click Apply si está en landing page."""
        if "greenhouse.io" not in self.page.url and "grnh.se" not in self.page.url:
            return False

        form_el = await self.page.query_selector("input#first_name, input#email, input#resume")
        if form_el and await form_el.is_visible():
            return True

        apply_selectors = [
            'button:has-text("Apply")',
            'a:has-text("Apply")',
            'button:has-text("Apply for this job")',
            'a:has-text("Apply for this job")',
        ]
        for sel in apply_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn:
                    print(f"[greenhouse] Clicking: '{await btn.inner_text().strip()}'")
                    await btn.click()
                    await self.page.wait_for_load_state("networkidle")
                    await self.page.wait_for_timeout(2000)
                    return True
            except Exception:
                continue
        return False

    async def authenticate(self) -> bool:
        """Greenhouse no requiere login para aplicar."""
        return True

    async def fill(self) -> FillResult:
        """Llena formulario Greenhouse inteligentemente."""
        self.filled = {}
        self.errors = []
        self.broken = []

        # 1. Datos básicos (first_name, last_name, email, phone)
        # Phone: solo dígitos, sin country code ni notas entre paréntesis
        raw_phone = self.candidate_data.get("phone", "")
        clean_phone = re.sub(r'\(.*?\)', '', raw_phone).strip()
        clean_phone = re.sub(r'^\+\d{1,3}\s*', '', clean_phone).replace(" ", "")
        basic_fields = {
            "first_name": self.candidate_data.get("first_name", ""),
            "last_name": self.candidate_data.get("last_name", ""),
            "email": self.candidate_data.get("email", ""),
            "phone": clean_phone,
        }
        print(f"[greenhouse] Filling basic fields: {list(basic_fields.keys())}")
        for field_id, value in basic_fields.items():
            if value:
                print(f"[greenhouse] Filling {field_id} = {value[:30]}...")
                success = await self._fill_text(f"input#{field_id}", value)
                if success:
                    print(f"[greenhouse] ✓ Filled {field_id}")
                else:
                    print(f"[greenhouse] ✗ Failed to fill {field_id}")

        # Country code for phone (separate field in Greenhouse) - phone country code +000
        print(f"[greenhouse] Filling phone country code combobox (+000 Your Country)")
        await self._fill_combobox("input#country", "Your Country")

        # 2. Los demás campos de texto (LinkedIn, GitHub, location, etc.) se llenan
        # en el paso 3 buscando por label - cubre required y opcionales.

        # 3. Llenar TODOS los inputs de texto visibles por label (LinkedIn, GitHub, location, etc.)
        # No solo los required - LinkedIn/GitHub suelen ser opcionales
        all_inputs = await self.page.query_selector_all(
            'input[type="text"], input[type="url"], input:not([type]), textarea'
        )
        for inp in all_inputs:
            try:
                if not await inp.is_visible():
                    continue
                field_id = await inp.get_attribute("id")
                if not field_id or field_id in self.filled:
                    continue
                # Saltar campos ya conocidos (basic fields, country, file inputs)
                if field_id in ("first_name", "last_name", "email", "phone", "country",
                                 "resume", "cover_letter", "gender", "hispanic_ethnicity",
                                 "veteran_status", "disability_status"):
                    continue

                role = await inp.get_attribute("role")
                if role == "combobox":
                    continue  # Los comboboxes se manejan aparte

                label = await self._get_label_text(field_id)
                value = self._get_value_for_label(label)
                if value:
                    print(f"[greenhouse] Filling {field_id} ({label[:40]}...) = {value[:40]}...")
                    await self._fill_text(f"#{field_id}", value)
            except Exception:
                continue

        # 4. Llenar campos required detectados dinámicamente (comboboxes y textos)
        required_inputs = await self.page.query_selector_all('[aria-required="true"]')
        for inp in required_inputs:
            field_id = await inp.get_attribute("id")
            if not field_id or field_id in self.filled:
                continue

            role = await inp.get_attribute("role")
            label = await self._get_label_text(field_id)
            value = self._get_value_for_label(label)

            if value:
                if role == "combobox":
                    await self._fill_combobox(f"#{field_id}", value)
                else:
                    await self._fill_text(f"#{field_id}", value)

        # 5. EEO comboboxes (opcionales pero recomendados)
        eeo_fields = {
            "#gender": "Male",
            "#hispanic_ethnicity": "No",
            "#veteran_status": "I am not a protected veteran",
            "#disability_status": "No, I don't have a disability",
        }
        for selector, value in eeo_fields.items():
            try:
                el = await self.page.query_selector(selector)
                if el and await el.is_visible():
                    await self._fill_combobox(selector, value)
            except Exception:
                pass

        # 6. Subir CV
        cv_path = self.candidate_data.get("cv_path", str(Path(__file__).resolve().parent.parent.parent / "cv.txt"))
        if cv_path:
            print(f"[greenhouse] Uploading CV from: {cv_path}")
            await self._upload_file('input#resume, input[type="file"][name="resume"], input[type="file"]', cv_path)
            await self.page.wait_for_timeout(1000)

        # 7. Cover letter si existe
        cl_path = self.candidate_data.get("cover_letter_path", "")
        if cl_path:
            await self._upload_file('input[name="cover_letter"], input[type="file"][name*="cover"]', cl_path)

        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )

    async def validate(self) -> FillResult:
        """Valida formulario: verifica errores visibles y campos required con valor real."""
        self.errors = []
        self.broken = []

        error_selectors = [".error", ".field-error", ".alert-danger", "[role='alert']"]
        for sel in error_selectors:
            try:
                els = await self.page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        text = (await el.inner_text()).strip().lower()
                        if text and "thank" not in text and "success" not in text:
                            self.errors.append(text[:200])
            except Exception:
                pass

        # Verificar campos required: deben tener valor real (input o select__single-value)
        required = await self.page.query_selector_all('[aria-required="true"]')
        for inp in required:
            field_id = await inp.get_attribute("id")
            if not field_id:
                continue
            role = await inp.get_attribute("role")
            label = await self._get_label_text(field_id)

            if role == "combobox":
                # react-select: valor vive en .select__single-value del contenedor
                value = await self.page.evaluate(f"""() => {{
                    const input = document.querySelector('#{field_id}');
                    if (!input) return '';
                    const container = input.closest('.select__container') ||
                                      input.closest('[class*="select"]')?.parentElement;
                    if (!container) return '';
                    const sv = container.querySelector('.select__single-value, [class*="single-value"]');
                    return sv ? sv.textContent.trim() : '';
                }}""")
                if not value:
                    self.errors.append(f"Required combobox empty: {label} ({field_id})")
            else:
                val = (await inp.input_value()).strip() if await inp.is_visible() else ""
                if not val and field_id not in self.filled:
                    self.errors.append(f"Required field empty: {label} ({field_id})")

        return FillResult(
            success=len(self.errors) == 0 and len(self.broken) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )

    async def submit_application(self) -> FillResult:
        """
        Submit + manejo de verificación por email (Zoho IMAP).

        Flujo:
        1. Click "Submit application"
        2. Si aparece pantalla de código de verificación:
           a. Esperar email de Greenhouse en Zoho (hasta 120s)
           b. Extraer código de 6 dígitos
           c. Pegarlo y confirmar
        3. Verificar éxito final (URL /thanks o texto de confirmación)
        """
        submit_selectors = [
            'button:has-text("Submit application")',
            'button:has-text("Submit Application")',
            'button:has-text("Submit")',
            'button[type="submit"]',
            'input[type="submit"][value*="Submit"]',
        ]

        clicked = False
        submit_time = None
        for sel in submit_selectors:
            try:
                el = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if el:
                    print(f"[greenhouse] Clicking submit: {sel}")
                    # UTC aware + 60s de margen (reloj de Zoho puede estar adelantado)
                    submit_time = datetime.now(timezone.utc) - timedelta(seconds=60)
                    await el.click()
                    clicked = True
                    break
            except Exception:
                continue

        if not clicked:
            return FillResult(success=False, error_message="No submit button found", filled_fields=self.filled)

        await self.page.wait_for_load_state("domcontentloaded")
        await self.page.wait_for_timeout(4000)

        # ¿Apareció pantalla de verificación por código?
        needs_code = await self._verification_screen_visible()
        print(f"[greenhouse] Verification screen: {needs_code}")

        if needs_code:
            zoho_email = self.candidate_data.get("zoho_email")
            zoho_pass = self.candidate_data.get("zoho_app_password")

            if not (zoho_email and zoho_pass):
                return FillResult(
                    success=False,
                    error_message="Verification required but Zoho credentials not configured",
                    filled_fields=self.filled,
                )

            print(f"[greenhouse] Waiting for NEW verification code via Zoho IMAP (since {submit_time:%H:%M:%S})...")
            try:
                from auto_apply.unified.zoho_imap import get_greenhouse_verification_code
                code = await get_greenhouse_verification_code(
                    email=zoho_email,
                    password=zoho_pass,
                    timeout=180,
                    since=submit_time,
                )
            except Exception as e:
                return FillResult(success=False, error_message=f"Zoho IMAP error: {e}", filled_fields=self.filled)

            if not code:
                return FillResult(success=False, error_message="No verification code received within 180s", filled_fields=self.filled)

            print(f"[greenhouse] NEW code received: {code} - filling...")
            if not await self._fill_verification_code(code):
                return FillResult(success=False, error_message="Could not fill verification code", filled_fields=self.filled)

            # Screenshot antes de confirmar
            try:
                await self.page.screenshot(path="/tmp/before_confirm.png")
            except Exception:
                pass

            # Confirmar código (botón Verify/Submit/Confirm)
            confirm_selectors = [
                'button:has-text("Verify")',
                'button:has-text("Confirm")',
                'button:has-text("Submit")',
                'button[type="submit"]',
            ]
            for sel in confirm_selectors:
                try:
                    btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                    if btn:
                        await btn.click()
                        print(f"[greenhouse] Clicked confirm: {sel}")
                        break
                except Exception:
                    continue

            await self.page.wait_for_load_state("domcontentloaded")
            await self.page.wait_for_timeout(4000)

            # Debug: screenshot del estado post-confirm
            try:
                await self.page.screenshot(path="/tmp/after_confirm.png", full_page=True)
                print(f"[greenhouse] Post-confirm URL: {self.page.url}")
                print("[greenhouse] Screenshot: /tmp/after_confirm.png")
            except Exception:
                pass

        return await self._verify_submission()

    async def _verification_screen_visible(self) -> bool:
        """Detecta si Greenhouse pide código de verificación post-submit."""
        code_selectors = [
            'input[name*="verification" i]',
            'input[name*="code" i]',
            'input[id*="verification" i]',
            'input[placeholder*="code" i]',
            'input[placeholder*="verification" i]',
            'input[autocomplete="one-time-code"]',
        ]
        for sel in code_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        # También por texto
        try:
            body = (await self.page.inner_text("body", timeout=3000)).lower()
            if "verification code" in body or "enter the code" in body or "check your email" in body:
                return True
        except Exception:
            pass
        return False

    def _get_value_for_label(self, label: str) -> str:
        """Determina valor basado en label del campo.
        Orden importa: patrones específicos ANTES que genéricos."""
        label_lower = label.lower()

        # Patrones específicos primero (evitan falsos positivos)
        if "sponsor" in label_lower or "visa" in label_lower or "work authoriz" in label_lower:
            return "No"
        if "ai" in label_lower and "consent" in label_lower:
            return "Yes"
        if "reliability engineering experience" in label_lower or "do you have" in label_lower and "experience" in label_lower:
            return "Yes"

        # Campos de texto
        if "linkedin" in label_lower:
            return self.candidate_data.get("linkedin", "")
        if "github" in label_lower:
            return self.candidate_data.get("github", "")
        if "portfolio" in label_lower or "website" in label_lower or "personal site" in label_lower:
            return self.candidate_data.get("portfolio", "")
        if "location" in label_lower or "ciudad" in label_lower:
            return self.candidate_data.get("location", "Your Country")
        if "postgres" in label_lower and ("year" in label_lower or "experience" in label_lower):
            return "10+ years managing Postgres clusters, extensions, replication, performance tuning"
        if "year" in label_lower and "experience" in label_lower:
            return "10+ years building AI/ML infrastructure, private AI platform with Ollama/vLLM on GPU nodes"
        if "notice" in label_lower or "availab" in label_lower:
            return self.candidate_data.get("notice_period", "Immediate")
        if "salary" in label_lower or "compensation" in label_lower:
            return self.candidate_data.get("salary_expectation", "Negotiable")
        if "reliability engineering" in label_lower or "experience" in label_lower:
            return "10+ years building and operating distributed systems, databases, infrastructure"

        return ""

    async def _fill_verification_code(self, code: str) -> bool:
        """
        Llena el security code de Greenhouse.
        La pantalla usa N inputs individuales estilo OTP (1 char por input).
        Detecta el patrón OTP y distribuye el código carácter por carácter.
        """
        try:
            await self.page.wait_for_timeout(1000)

            # Patrón OTP: múltiples inputs visibles de 1 char (maxlength=1 o pequeño)
            otp_inputs = await self.page.evaluate("""
                Array.from(document.querySelectorAll('input'))
                    .filter(i => {
                        if (i.type === 'hidden' || i.type === 'file') return false;
                        if (i.offsetParent === null) return false;  // no visible
                        const ml = parseInt(i.getAttribute('maxlength') || '999');
                        return ml <= 2;
                    })
                    .map(i => ({name: i.name, id: i.id, maxlength: i.getAttribute('maxlength')}))
            """)

            if otp_inputs and len(otp_inputs) >= len(code) - 2:
                # Es OTP: obtener los ElementHandles visibles en orden DOM
                all_inputs = await self.page.query_selector_all(
                    'input[maxlength="1"], input[maxlength="2"]'
                )
                visible = []
                for inp in all_inputs:
                    try:
                        if await inp.is_visible():
                            visible.append(inp)
                    except Exception:
                        continue

                print(f"[greenhouse] OTP pattern detected: {len(visible)} single-char inputs")
                if len(visible) >= len(code):
                    # Llenar carácter por carácter
                    for i, char in enumerate(code):
                        box = visible[i]
                        await box.click()
                        await box.fill("")  # limpiar
                        await self.page.keyboard.type(char, delay=50)
                        await self.page.wait_for_timeout(100)

                    # Verificar valores
                    filled_ok = await self.page.evaluate(f"""
                        (() => {{
                            const inputs = Array.from(document.querySelectorAll('input'))
                                .filter(i => i.type !== 'hidden' && i.type !== 'file' &&
                                             i.offsetParent !== null &&
                                             parseInt(i.getAttribute('maxlength') || '999') <= 2);
                            const joined = inputs.map(i => i.value).join('');
                            return joined;
                        }})()
                    """)
                    print(f"[greenhouse] OTP boxes now: '{filled_ok}'")
                    if filled_ok == code:
                        print(f"[greenhouse] ✓ OTP code filled correctly: {code}")
                        return True
                    # Segundo intento: fill() directo por input
                    for i, char in enumerate(code):
                        try:
                            await visible[i].fill(char)
                            await self.page.wait_for_timeout(80)
                        except Exception:
                            pass
                    filled_ok2 = await self.page.evaluate("""
                        (() => {
                            const inputs = Array.from(document.querySelectorAll('input'))
                                .filter(i => i.type !== 'hidden' && i.type !== 'file' &&
                                             i.offsetParent !== null &&
                                             parseInt(i.getAttribute('maxlength') || '999') <= 2);
                            return inputs.map(i => i.value).join('');
                        })()
                    """)
                    if filled_ok2 == code:
                        print(f"[greenhouse] ✓ OTP code filled (2nd attempt): {code}")
                        return True

            # Fallback: input único de código
            selectors = [
                'input[name*="security_code" i]',
                'input[name*="verification" i]',
                'input[name*="code" i]',
                'input[id*="security" i]',
                'input[autocomplete="one-time-code"]',
            ]
            for selector in selectors:
                try:
                    el = await self.page.wait_for_selector(selector, state="visible", timeout=1500)
                    if el:
                        await el.fill(code)
                        await self.page.wait_for_timeout(300)
                        val = (await el.input_value()).strip()
                        if val == code:
                            print(f"[greenhouse] ✓ Filled security code via {selector}: {code}")
                            return True
                except Exception:
                    continue

            # Debug: screenshot + listar inputs visibles
            try:
                await self.page.screenshot(path="/tmp/security_code_screen.png", full_page=True)
                inputs_info = await self.page.evaluate("""
                    Array.from(document.querySelectorAll('input')).map(i => ({
                        name: i.name, id: i.id, type: i.type,
                        maxlength: i.getAttribute('maxlength'),
                        visible: i.offsetParent !== null
                    }))
                """)
                print(f"[greenhouse] ✗ Could not fill code. Inputs: {inputs_info}")
                print("[greenhouse] Screenshot: /tmp/security_code_screen.png")
            except Exception:
                pass
            return False
        except Exception as e:
            print(f"[greenhouse] Error filling verification code: {e}")
            return False