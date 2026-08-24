"""
Filler específico para Lever ATS.

Lever usa estructura consistente:
- Posting: jobs.lever.co/{company}/{hash}
- Botón "Apply for this job" abre el form inline (a veces en la misma URL)
- Inputs con name="name"|"email"|"phone"|"urls[LinkedIn]"|etc.
- Cards de upload: input[type=file] dentro de .application-facet / [data-qa]
- Preguntas custom: .application-question con <label> asociado
- Selects nativos y checkboxes/radios
- Submit: button[type=submit] "Submit Application"
- Confirmación: "Application received!" / thanks page

Sin OTP por email normalmente — flujo directo a confirmación.
"""
import logging
import re
from typing import Any, Optional
from playwright.async_api import Page
from .fillers import ATSBaseFiller, FillResult, register_filler

logger = logging.getLogger(__name__)


@register_filler("lever")
class LeverFiller(ATSBaseFiller):
    """Filler especializado para Lever."""

    async def analyze(self) -> dict:
        """Analiza estructura Lever."""
        try:
            await self.page.wait_for_selector(
                'form, [data-qa="application-form"], .application-page, .page-application',
                timeout=10000,
            )
        except Exception:
            pass

        fields = await self.page.query_selector_all(
            'input:not([type="hidden"]):not([type="file"]), select, textarea'
        )
        field_info = []
        for f in fields:
            name = await f.get_attribute("name")
            field_type = await f.get_attribute("type")
            tag = await f.evaluate("el => el.tagName.toLowerCase()")
            if name:
                field_info.append({"name": name, "type": field_type or tag, "tag": tag})

        has_form = bool(await self.page.query_selector('form'))
        return {
            "fields": field_info,
            "ats": "lever",
            "has_apply_form": has_form,
        }

    async def navigate(self) -> bool:
        """Click 'Apply' si estamos en la landing del posting."""
        if "lever.co" not in self.page.url:
            return False

        # Si el form ya está visible, no hay nada que hacer
        form_visible = False
        try:
            el = await self.page.wait_for_selector(
                'form textarea, form input[name="name"], .application-facet',
                state="visible",
                timeout=2500,
            )
            form_visible = bool(el)
        except Exception:
            pass
        if form_visible:
            return True

        apply_selectors = [
            'a:has-text("Apply for this job")',
            'button:has-text("Apply for this job")',
            'a[data-qa="show-applied"]',
            'button:has-text("Apply")',
            'a:has-text("Apply")',
        ]
        for sel in apply_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=2000)
                if btn:
                    await btn.click()
                    await self.page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue
        # Algunos boards muestran el form directamente
        return True

    async def authenticate(self) -> bool:
        """Lever no requiere login para aplicar."""
        return True

    async def _dismiss_cookie_banner(self):
        """Cierra banners de consentimiento de cookies que tapan el form."""
        consent_texts = ["accept all", "accept", "allow all", "allow", "agree", "got it", "ok"]
        for _ in range(3):
            dismissed = False
            for sel in [
                'button:has-text("Accept all")', 'button:has-text("Accept All")',
                'button:has-text("Accept")', 'button:has-text("ALLOW ALL")',
                'button:has-text("Allow")', 'button:has-text("Agree")',
                'button:has-text("Got it")', '#onetrust-accept-btn-handler',
                '[class*="cookie"] button', '[id*="cookie"] button',
                '[class*="consent"] button',
            ]:
                try:
                    btn = await self.page.query_selector(sel)
                    if btn and await btn.is_visible():
                        text = ((await btn.inner_text()) or "").strip().lower()
                        if any(ct in text for ct in consent_texts) or "cookie" in sel or "consent" in sel or "onetrust" in sel:
                            await btn.click(timeout=2000)
                            await self.page.wait_for_timeout(800)
                            dismissed = True
                            logger.info(f"Lever: cookie banner cerrado ('{text[:30]}')")
                            break
                except Exception:
                    continue
            if not dismissed:
                break

    async def fill(self) -> FillResult:
        """Llena formulario Lever completo."""
        self.filled = {}
        self.errors = []
        self.broken = []

        # 0. Esperar form activo y limpiar banners que tapan campos
        try:
            await self.page.wait_for_selector(
                'form input, form textarea', state="visible", timeout=8000
            )
        except Exception:
            self.broken.append("form-not-visible")
        await self._dismiss_cookie_banner()

        # 1. Campos básicos por name (estructura estándar Lever)
        # Fill silencioso: si el campo no existe en este form, NO es error
        full_name = (
            f"{self.candidate_data.get('first_name', '')} "
            f"{self.candidate_data.get('last_name', '')}"
        ).strip()

        raw_phone = self.candidate_data.get("phone", "")
        clean_phone = re.sub(r"\(.*?\)", "", raw_phone).strip()
        clean_phone = re.sub(r"^\+\d{1,3}\s*", "", clean_phone).replace(" ", "")

        basic_fields = [
            # (selector, valor, key)
            ('input[name="name"]', full_name, "full_name"),
            ('input[name="firstName"]', self.candidate_data.get("first_name", ""), "first_name"),
            ('input[name="lastName"]', self.candidate_data.get("last_name", ""), "last_name"),
            ('input[name="email"]', self.candidate_data.get("email", ""), "email"),
            ('input[name="phone"]', clean_phone, "phone"),
            ('input[name="location"]', self.candidate_data.get("location", ""), "location"),
            ('input[name="linkedin"]', self.candidate_data.get("linkedin", ""), "linkedin"),
            ('input[name="github"]', self.candidate_data.get("github", ""), "github"),
            ('input[name="portfolio"]', self.candidate_data.get("portfolio", ""), "portfolio"),
            # Variante nueva de Lever: urls[LinkedIn] etc.
            ('input[name="urls[LinkedIn]"]', self.candidate_data.get("linkedin", ""), "linkedin"),
            ('input[name="urls[GitHub]"]', self.candidate_data.get("github", ""), "github"),
            ('input[name="urls[Portfolio]"]', self.candidate_data.get("portfolio", ""), "portfolio"),
            ('input[name="urls[Other Website]"]', self.candidate_data.get("portfolio", ""), "website"),
        ]
        for sel, value, key in basic_fields:
            if value and value.strip():
                ok = await self._fill_text_quiet(sel, value)
                if ok:
                    self.filled[key] = value

        # 2. Segunda pasada: campos required visibles que quedaron vacíos
        #    (el form nuevo de Lever usa inputs sin name o hidden duplicates)
        await self._fill_missing_by_label()

        # 3. Subir CV antes de preguntas (algunas validan resume primero)
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_cv(cv_path)
            # Las preguntas custom suelen cargar lazy tras analizar el resume
            await self.wait_for_resume_analysis(timeout_s=20)
            try:
                await self.page.wait_for_selector(
                    "li.application-question, .application-question",
                    state="visible", timeout=10000,
                )
            except Exception:
                pass

        # 4. Cover letter (opcional)
        cl_path = self.candidate_data.get("cover_letter_path", "")
        if cl_path:
            await self._upload_cover_letter(cl_path)

        # 5. Preguntas custom (label-based, igual que Greenhouse)
        #    + soporte multi-paso: algunos boards dividen el form en páginas
        #    con botón Continue; llenamos cada página antes de avanzar.
        for page_num in range(5):
            await self._answer_custom_questions()
            await self._fill_missing_by_label(final_pass=(page_num > 0))

            next_btn = await self._find_continue_button()
            if not next_btn:
                break  # Última página (solo queda Submit)
            logger.info(f"Lever: avanzando a página {page_num + 2} del form")
            await next_btn.click()
            await self.page.wait_for_timeout(2500)

        # 6. Última pasada: required que sigan vacíos
        await self._answer_custom_questions()
        await self._fill_missing_by_label(final_pass=True)

        # 7. EEO/demographics: sección opcional, saltar o responder mínimo
        await self._handle_eeo_section()

        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )

    async def _fill_text_quiet(self, selector: str, value: str) -> bool:
        """Fill silencioso: False si el campo no existe (sin registrar error)."""
        try:
            el = await self.page.wait_for_selector(selector, state="visible", timeout=1500)
            if not el:
                return False
            # Si ya tiene valor (ej. llenado por pasada anterior), sobreescribir
            await el.fill(value)
            return True
        except Exception:
            return False

    async def _fill_missing_by_label(self, final_pass: bool = False):
        """Segunda pasada: inputs visibles vacíos → resolver label → llenar.

        Cubre el layout nuevo de Lever donde los inputs no tienen name
        utilizable o existen duplicates hidden.
        """
        try:
            inputs = await self.page.query_selector_all(
                'input[type="text"], input[type="email"], input[type="tel"], input[type="url"], input:not([type]), textarea'
            )
        except Exception:
            return
        for inp in inputs:
            try:
                if not await inp.is_visible():
                    continue
                val = (await inp.input_value() or "").strip()
                if val:
                    continue
                typ = (await inp.get_attribute("type") or "").lower()
                if typ in ("file", "hidden", "checkbox", "radio", "submit", "button"):
                    continue
                if await inp.is_disabled():
                    continue
                label_text = await self._label_for_input(inp)
                if not label_text:
                    continue
                answer = self._get_value_for_label(label_text)
                if answer:
                    await inp.fill(answer)
                    self.filled[f"label:{label_text[:50]}"] = answer
                    logger.info(f"Lever: '{label_text[:50]}' llenado por label (pass2)")
                elif final_pass:
                    # Required sin respuesta conocida → marcar para revisión
                    required = await inp.get_attribute("required")
                    aria_req = (await inp.get_attribute("aria-required") or "").lower()
                    if required is not None or aria_req == "true":
                        self.errors.append(f"No answer for required: {label_text[:80]}")
            except Exception:
                continue

    async def _label_for_input(self, inp) -> Optional[str]:
        """Resuelve el texto del label de un input (varias estrategias)."""
        # 1. aria-label / placeholder como fallback semántico
        for attr in ("aria-label", "placeholder"):
            v = await inp.get_attribute(attr)
            if v and len(v.strip()) > 2 and len(v.strip()) < 200:
                # placeholder tipo "telephone" no sirve como pregunta; solo
                # usar si parece pregunta (contiene espacio o termina en ?)
                t = v.strip()
                if attr == "placeholder" and " " not in t and not t.endswith("?"):
                    continue
                return t
        # 2. label[for=id]
        iid = await inp.get_attribute("id")
        if iid:
            try:
                lbl = await self.page.query_selector(f'label[for="{iid}"]')
                if lbl:
                    t = ((await lbl.inner_text()) or "").strip()
                    if t:
                        return t
            except Exception:
                pass
        # 3. label ancestro
        try:
            anc = await inp.evaluate_handle("el => el.closest('label')")
            el = anc.as_element()
            if el:
                t = ((await el.inner_text()) or "").strip()
                if t:
                    return t
        except Exception:
            pass
        # 4. label dentro del contenedor de pregunta
        try:
            anc = await inp.evaluate_handle(
                "el => el.closest('.application-question, [data-qa*=\"question\"], div.application-facet, fieldset, form')"
            )
            el = anc.as_element()
            if el:
                lbl = await el.query_selector("label")
                if lbl:
                    t = ((await lbl.inner_text()) or "").strip()
                    if t:
                        return t
        except Exception:
            pass
        return None

    async def _find_continue_button(self):
        """Encuentra botón Continue/Next (NO Submit) si hay más páginas."""
        continue_selectors = [
            'button:has-text("Continue")',
            'button:has-text("Next")',
            'input[type="submit"][value*="Continue"]',
        ]
        for sel in continue_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=1200)
                if btn and await btn.is_enabled():
                    # Excluir que sea el submit final
                    text = ((await btn.inner_text()) or "").lower()
                    if "submit" in text:
                        continue
                    return btn
            except Exception:
                continue
        return None

    async def _upload_cv(self, cv_path: str):
        """Sube CV en Lever."""
        selectors = [
            'input[type="file"][accept*="pdf"]',
            'input[name="resume"]',
            'input[data-qa="resume-upload"]',
            '.application-facet input[type="file"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            try:
                el = await self.page.wait_for_selector(sel, timeout=2500)
                if el:
                    await el.set_input_files(cv_path)
                    # Lever muestra el nombre del archivo subido
                    await self.page.wait_for_timeout(2000)
                    uploaded = await self.page.query_selector(
                        '[data-qa="file-name"], .attachment-card, .filename'
                    )
                    self.filled["resume"] = (
                        (await uploaded.inner_text()).strip()
                        if uploaded else cv_path.split("/")[-1]
                    )
                    logger.info(f"Lever: CV subido ({self.filled['resume']})")
                    return True
            except Exception:
                continue
        self.broken.append("cv-upload")
        return False

    async def _upload_cover_letter(self, cl_path: str):
        """Sube cover letter."""
        selectors = [
            'input[name="coverLetter"]',
            'input[name="cover_letter"]',
            'input[data-qa="cover-letter-upload"]',
        ]
        for sel in selectors:
            try:
                el = await self.page.wait_for_selector(sel, timeout=2000)
                if el:
                    await el.set_input_files(cl_path)
                    await self.page.wait_for_timeout(1500)
                    self.filled["cover_letter"] = cl_path.split("/")[-1]
                    return True
            except Exception:
                continue
        return False

    def _get_value_for_label(self, label: str) -> Optional[str]:
        """Mapea label de pregunta custom → respuesta del perfil."""
        label_lower = label.lower().strip()
        cd = self.candidate_data

        # 0. Respuestas configuradas por el usuario (más específico primero)
        qa = cd.get("question_answers") or {}
        for keyword, answer in sorted(
            qa.items(), key=lambda kv: len(str(kv[0])), reverse=True
        ):
            if str(keyword).lower() in label_lower and answer:
                return str(answer)

        # Orden importante: patrones específicos ANTES que genéricos
        if "sponsor" in label_lower or ("visa" in label_lower and "sponsorship" in label_lower):
            return cd.get("requires_sponsorship_answer", "No")
        if "authorized" in label_lower or "authorised" in label_lower or "work authorization" in label_lower or "eligible" in label_lower:
            return "Yes"
        if "how" in label_lower and ("hear" in label_lower or "came across" in label_lower or "find" in label_lower or "learn" in label_lower):
            return cd.get("how_heard_answer", "Online job posting")
        if "phone" in label_lower or "mobile" in label_lower or "tel" in label_lower:
            raw = cd.get("phone", "")
            clean = re.sub(r"\(.*?\)", "", raw).strip()
            clean = re.sub(r"^\+\d{1,3}\s*", "", clean).replace(" ", "")
            return clean or None
        if "visa" in label_lower:
            return cd.get("visa_status", "No visa required for remote work")
        if "notice" in label_lower or "availab" in label_lower or "start" in label_lower:
            return cd.get("notice_period", "Immediate")
        if "salary" in label_lower or "compensation" in label_lower or "expectation" in label_lower:
            return cd.get("salary_expectation", "Negotiable")
        if "years" in label_lower and ("experience" in label_lower or "professional" in label_lower):
            return cd.get("years_experience", "10+")
        if "english" in label_lower and ("level" in label_lower or "proficiency" in label_lower or "how" in label_lower):
            return cd.get("english_level", "Advanced")
        if "gender" in label_lower:
            return None  # EEO - no responder
        if "linkedin" in label_lower:
            return cd.get("linkedin", "")
        if "github" in label_lower or "gitlab" in label_lower:
            return cd.get("github", "")
        if "website" in label_lower or "portfolio" in label_lower or "blog" in label_lower:
            return cd.get("portfolio", "")
        if "location" in label_lower or "based" in label_lower or "where" in label_lower:
            return cd.get("location", "") or None
        if "relocate" in label_lower:
            return "No"
        if "remote" in label_lower and ("work" in label_lower or "ok" in label_lower or "comfortable" in label_lower):
            return "Yes"
        if "first name" in label_lower:
            return cd.get("first_name", "")
        if "last name" in label_lower or "surname" in label_lower:
            return cd.get("last_name", "")
        if "full name" in label_lower or label_lower.strip() == "name":
            return (
                f"{cd.get('first_name', '')} {cd.get('last_name', '')}".strip() or None
            )
        if "email" in label_lower:
            return cd.get("email", "")
        if "company" in label_lower and "current" in label_lower:
            return cd.get("current_company") or None

        # Preguntas aprendidas de aplicaciones previas
        try:
            from job_data import application_data
            learned = application_data.get_value_for_label(label_lower)
            if learned:
                # Blacklist: respuestas basura guardadas en sesiones rotas
                garbage = {
                    "telephone", "email", "name", "url", "n/a", "na", "phone",
                    "text", "answer", "your answer", "placeholder", "location",
                }
                if learned.strip().lower() not in garbage and learned.strip().lower() not in label_lower:
                    return learned.strip()
        except Exception:
            pass
        return None

    async def _answer_custom_questions(self):
        """Responde preguntas custom de Lever por label."""
        questions = await self.page.query_selector_all(
            "li.application-question, .application-question, [data-qa*='question'], div.question"
        )
        if not questions:
            # Retry: pueden estar cargando lazy
            await self.page.wait_for_timeout(3000)
            questions = await self.page.query_selector_all(
                "li.application-question, .application-question, [data-qa*='question'], div.question"
            )
        logger.info(f"Lever: {len(questions)} preguntas custom detectadas")
        for q in questions:
            try:
                # Label de la pregunta (form nuevo: div.application-label > .text;
                # form viejo: <label> suelto, h3, legend)
                label_el = await q.query_selector(
                    ".application-label .text, .application-label, "
                    "label:not(:has(input)):not(:has(select)):not(:has(textarea)), "
                    "h3, legend"
                )
                if not label_el:
                    logger.info("Lever: pregunta sin label reconocible, skip")
                    continue
                label_text = ((await label_el.inner_text()) or "").strip()
                if not label_text or len(label_text) > 300:
                    logger.info(f"Lever: label vacío o muy largo, skip")
                    continue

                answer = self._get_value_for_label(label_text)

                # Input text/email/url/textarea dentro de la pregunta
                inp = await q.query_selector(
                    'input[type="text"], input[type="email"], input[type="url"], textarea'
                )
                if inp:
                    if answer:
                        await inp.fill(answer)
                        self.filled[label_text[:60]] = answer
                    continue

                # Select nativo
                sel_el = await q.query_selector("select")
                if sel_el:
                    if answer:
                        ok = await self._select_native_option(sel_el, answer, label_text)
                        if ok:
                            self.filled[label_text[:60]] = answer
                    continue

                # Radios: estrategia completa (match, rangos, gradación, yes/no)
                radios = await q.query_selector_all('input[type="radio"]')
                if radios:
                    logger.info(
                        f"Lever: radio-question '{label_text[:40]}' answer={answer!r} n={len(radios)}"
                    )
                    if answer is None:
                        # EEO u opt-out: marcar "prefer not/decline" si existe
                        await self._pick_radio(radios, ["prefer not", "decline", "do not"])
                    else:
                        already = False
                        for r in radios:
                            if await r.is_checked():
                                already = True
                                break
                        if not already:
                            picked = await self._pick_radio_smart(radios, answer, label_text)
                            logger.info(f"Lever: pick_radio_smart -> {picked}")
                            if picked:
                                self.filled[label_text[:60]] = answer
                    continue

                # Checkboxes de consentimiento
                checks = await q.query_selector_all('input[type="checkbox"]')
                if checks and answer and len(checks) == 1:
                    checked = await checks[0].is_checked()
                    if answer.lower() == "yes" and not checked:
                        await checks[0].check()
                        self.filled[label_text[:60]] = answer
            except Exception as e:
                logger.warning(f"Lever question error: {type(e).__name__}: {e}")

    async def _select_native_option(self, sel_el, answer: str, label: str) -> bool:
        """Selecciona opción de <select> nativo cuyo texto matchee."""
        try:
            options = await sel_el.query_selector_all("option")
            ans_low = answer.lower()
            best = None
            for opt in options:
                text = ((await opt.inner_text()) or "").strip().lower()
                value = await opt.get_attribute("value")
                if not value:
                    continue
                if text == ans_low or value.lower() == ans_low:
                    best = value
                    break
                if ans_low in text or text in ans_low:
                    best = best or value
            if best is None and options and len(options) > 1:
                # Fallback: primera opción con valor no vacío (evita placeholder)
                for opt in options:
                    v = await opt.get_attribute("value")
                    t = ((await opt.inner_text()) or "").lower()
                    if v and ("select" not in t and "choose" not in t):
                        best = v
                        break
            if best is not None:
                await sel_el.select_option(value=best)
                return True
        except Exception as e:
            logger.debug(f"Lever select error ({label}): {e}")
        return False

    @staticmethod
    def _norm(s: str) -> str:
        """Normaliza texto para matching (lowercase, sin acentos, 1 espacio)."""
        import unicodedata
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return re.sub(r"\s+", " ", s.lower().strip())

    async def _radio_option_text(self, r) -> str:
        """Texto visible de una opción radio (value attr o span hermano)."""
        val = (await r.get_attribute("value")) or ""
        if val:
            return val
        try:
            # <label><input><span class="application-answer-alternative">Text</span></label>
            span = await r.evaluate_handle(
                "el => el.closest('label')?.querySelector('span')"
            )
            el = span.as_element()
            if el:
                return ((await el.inner_text()) or "").strip()
        except Exception:
            pass
        return ""

    async def _pick_radio(self, radios, keywords) -> bool:
        for r in radios:
            try:
                parent_text = (await self._radio_option_text(r)).lower()
                if not parent_text:
                    rid = await r.get_attribute("id")
                    if rid:
                        lbl = await self.page.query_selector(f'label[for="{rid}"]')
                        if lbl:
                            parent_text = ((await lbl.inner_text()) or "").lower()
                if any(self._norm(kw) in self._norm(parent_text) for kw in keywords):
                    await r.check()
                    return True
            except Exception:
                continue
        return False

    async def _pick_radio_by_yesno(self, radios, answer: str) -> bool:
        want = "yes" if answer.lower() == "yes" else "no"
        return await self._pick_radio(radios, [want])

    async def _js_check_radio(self, r) -> bool:
        """Marca radio via JS: bypass de overlays (hCaptcha iframe superpuesto)."""
        try:
            await r.evaluate(
                "el => { el.click(); el.checked = true;"
                " el.dispatchEvent(new Event('input', {bubbles: true}));"
                " el.dispatchEvent(new Event('change', {bubbles: true})); }"
            )
            return await r.is_checked()
        except Exception:
            return False

    async def _pick_radio_smart(self, radios, answer: str, label: str) -> bool:
        """Estrategia completa para radios:
        1. Match exacto/parcial del answer contra el value de cada opción
        2. Si answer es numérico de años y las opciones son rangos → mejor rango
        3. Gradación de experiencia (no/some/extensive) → intermedia conservadora
        4. Fallback yes/no
        """
        ans = self._norm(answer)
        ans_years = None
        m = re.match(r"^(\d+)", ans)
        if m:
            ans_years = int(m.group(1))

        # 1. Match directo contra values
        texts = []
        for r in radios:
            try:
                texts.append(await self._radio_option_text(r))
            except Exception:
                texts.append("")
        normed = [self._norm(t) for t in texts]

        for r, nval in zip(radios, normed):
            if nval and (nval == ans or ans in nval or (len(ans) > 3 and nval in ans)):
                try:
                    await r.check(timeout=2000)
                    return True
                except Exception:
                    try:
                        await r.check(force=True, timeout=2000)
                        return True
                    except Exception:
                        # Overlay (hCaptcha) intercepta el click → JS directo
                        return await self._js_check_radio(r)

        # 2. Rangos de años: "Less than 3 years" / "More than 5 years" / "5+ years"
        if ans_years is not None:
            best_idx, best_cap = None, -1
            for i, nval in enumerate(normed):
                if not nval:
                    continue
                # Descartar opciones de "sin experiencia"
                if "don" in nval and "experience" in nval and "any" in nval:
                    continue
                nums = [int(x) for x in re.findall(r"\d+", nval)]
                if not nums:
                    continue
                cap = max(nums)
                if "less" in nval or "under" in nval:
                    cap = min(nums) - 1  # "Less than 3" => max 2
                if cap <= ans_years and cap > best_cap:
                    best_idx, best_cap = i, cap
            if best_idx is not None:
                try:
                    await radios[best_idx].check(timeout=2000)
                    return True
                except Exception:
                    try:
                        await radios[best_idx].check(force=True, timeout=2000)
                        return True
                    except Exception:
                        return await self._js_check_radio(radios[best_idx])

        # 3. Gradación sin número en answer (ej: "Some experience"):
        #    elegir la opción intermedia si hay 3+ opciones de gradación
        gradation_kw = ("experience", "proficien", "knowledge", "familiar")
        if any(kw in self._norm(label) for kw in gradation_kw) and len(radios) >= 3:
            mid = len(radios) // 2
            try:
                await radios[mid].check()
                return True
            except Exception:
                pass

        # 4. Yes/No
        return await self._pick_radio_by_yesno(radios, answer)

    async def _handle_eeo_section(self):
        """Sección EEO/demographics de Lever: opcional, dejar en blanco."""
        # No interactuamos: Lever permite enviar sin completar EEO
        pass

    async def validate(self) -> FillResult:
        """Valida formulario Lever: busca errores visibles."""
        self.errors = []
        self.broken = []

        error_selectors = [
            "[data-qa='error-message']",
            ".field-error",
            "label.error",
            "[role='alert']",
        ]
        for sel in error_selectors:
            try:
                els = await self.page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        text = ((await el.inner_text()) or "").strip()
                        if text and "thank" not in text.lower():
                            self.errors.append(text[:200])
            except Exception:
                pass

        # Campos required vacíos visibles (por atributo o por label con ✱)
        try:
            inputs = await self.page.query_selector_all(
                'input[type="text"], input[type="email"], input[type="tel"], input[type="url"], input:not([type]), textarea'
            )
            for e_el in inputs[:30]:
                try:
                    if not await e_el.is_visible():
                        continue
                    val = (await e_el.input_value() or "").strip()
                    if val:
                        continue
                    typ = (await e_el.get_attribute("type") or "").lower()
                    if typ in ("file", "hidden", "checkbox", "radio", "submit", "button"):
                        continue
                    required = await e_el.get_attribute("required")
                    aria_req = (await e_el.get_attribute("aria-required") or "").lower()
                    if required is None and aria_req != "true":
                        # Detectar por asterisco en el label
                        label_text = (await self._label_for_input(e_el) or "")
                        if "✱" not in label_text and "*" not in label_text:
                            continue
                    name = await e_el.get_attribute("name") or await self._label_for_input(e_el) or "unknown"
                    self.errors.append(f"Required empty: {name[:80]}")
                except Exception:
                    continue
        except Exception:
            pass

        # Captcha presente → bloqueante para auto-submit
        try:
            if await self.has_captcha():
                self.broken.append("captcha-present")
        except Exception:
            pass

        return FillResult(
            success=len(self.errors) == 0 and len(self.broken) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )

    # Captchas comunes en Lever (GeeTest, hCaptcha, reCAPTCHA, Turnstile)
    CAPTCHA_SELECTORS = [
        'iframe[src*="geetest"]',
        '[class*="geetest"]',
        'div[class*="geetest"]',
        'iframe[src*="hcaptcha"]',
        '.h-captcha',
        '[data-hcaptcha-widget-id]',
        'iframe[src*="recaptcha"]',
        '.g-recaptcha',
        'iframe[src*="challenges.cloudflare"]',
        '.cf-turnstile',
    ]

    async def has_captcha(self) -> bool:
        """Detecta si hay un captcha visible en la página."""
        for sel in self.CAPTCHA_SELECTORS:
            try:
                el = await self.page.query_selector(sel)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def wait_for_resume_analysis(self, timeout_s: int = 30):
        """Espera a que Lever termine de analizar el resume subido."""
        try:
            await self.page.wait_for_selector(
                'text=Analyzing resume', state="hidden", timeout=timeout_s * 1000
            )
        except Exception:
            pass  # best-effort

    async def submit_application(self) -> FillResult:
        """Submit final + verificación de confirmación Lever."""
        # 0. ¿El humano ya submiteó durante el review gate?
        pre = await self._verify_lever_submission(quick=True)
        if pre.success:
            return pre

        # 1. Esperar análisis de resume (el submit puede fallar antes)
        await self.wait_for_resume_analysis()

        # 2. Captcha: esperar a que el humano lo resuelva (semi-auto)
        if await self.has_captcha():
            logger.info("Lever: captcha detectado, esperando resolución humana (90s)...")
            deadline = 90
            while deadline > 0 and await self.has_captcha():
                await self.page.wait_for_timeout(3000)
                deadline -= 3
            if await self.has_captcha():
                await self._screenshot("lever_captcha_blocked")
                return FillResult(
                    success=False,
                    error_message="CAPTCHA present and not resolved - use semi-auto mode",
                    filled_fields=self.filled,
                )
            logger.info("Lever: captcha resuelto, continuando submit")

        # 3. Scroll al fondo para asegurar visibilidad del botón
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self.page.wait_for_timeout(500)

        submit_selectors = [
            'button[type="submit"]:has-text("Submit Application")',
            'button:has-text("Submit Application")',
            'button[type="submit"]:has-text("Submit application")',
            'button:has-text("Submit application")',
            'button[type="submit"]:has-text("Submit")',
            'input[type="submit"]',
        ]
        for sel in submit_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn:
                    await btn.click()
                    logger.info("Lever: submit clicked")
                    # Lever procesa async; esperar señal
                    await self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                    return await self._verify_lever_submission()
            except Exception:
                continue

        return FillResult(success=False, error_message="No Lever submit button found")

    async def _verify_lever_submission(self, quick: bool = False) -> FillResult:
        """Verifica confirmación de Lever (más tolerante que el base)."""
        import asyncio

        success_signals = [
            "application received",
            "thanks for applying",
            "thank you for applying",
            "your application has been received",
            "we've received your application",
            "application submitted",
            "successfully applied",
        ]
        if quick:
            # Solo chequeo inmediato (para detectar submit humano previo)
            try:
                url = self.page.url.lower()
                if any(p in url for p in ("/thanks", "/confirmation", "/success")):
                    return FillResult(success=True, filled_fields=self.filled)
                body = (await self.page.inner_text("body", timeout=2000)).lower()
                if any(s in body for s in success_signals):
                    return FillResult(success=True, filled_fields=self.filled)
            except Exception:
                pass
            return FillResult(success=False, error_message="not submitted yet")

        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            url = self.page.url.lower()
            if any(p in url for p in ("/thanks", "/confirmation", "/success")):
                await self._screenshot("lever_confirmation")
                return FillResult(success=True, filled_fields=self.filled)
            try:
                body = (await self.page.inner_text("body", timeout=3000)).lower()
                if any(s in body for s in success_signals):
                    await self._screenshot("lever_confirmation")
                    return FillResult(success=True, filled_fields=self.filled)
                # Form desapareció y no hay errores = probablemente enviado
                form_gone = not await self.page.query_selector(
                    'form input[name="email"], form textarea'
                )
                if form_gone and "error" not in body[:2000]:
                    await self.page.wait_for_timeout(2000)
                    body2 = (await self.page.inner_text("body", timeout=3000)).lower()
                    if any(s in body2 for s in success_signals):
                        await self._screenshot("lever_confirmation")
                        return FillResult(success=True, filled_fields=self.filled)
            except Exception:
                pass
            await self.page.wait_for_timeout(1000)

        await self._screenshot("lever_no_confirmation")
        return FillResult(
            success=False,
            error_message="No Lever confirmation detected after submit",
            filled_fields=self.filled,
        )
