"""
Filler específico para Ashby ATS.

Ashby (jobs.ashbyhq.com/{org}/{id}):
- SPA React; el form vive en .../application
- Campos de sistema: input[name="_systemfield_name"], _systemfield_email
- Custom questions: inputs/textarea con name=UUID + <label> asociado
- Resume: input[type=file] con card "Upload file"
- Submit directo: button "Submit Application" (algunos boards multi-step)
- Confirmación: "Application received" / página de gracias
- Sin captcha en la gran mayoría de boards → full-auto friendly

Hereda helpers probados de LeverFiller (radio smart picker, label
resolver, question_answers, JS fallback para overlays).
"""
import logging
import re
from typing import Optional
from playwright.async_api import Page
from .fillers import FillResult, register_filler
from .fillers_lever import LeverFiller

logger = logging.getLogger(__name__)


@register_filler("ashby")
class AshbyFiller(LeverFiller):
    """Filler especializado para Ashby (reutiliza lógica de Lever)."""

    async def analyze(self) -> dict:
        """Analiza estructura Ashby."""
        try:
            await self.page.wait_for_selector(
                'input[name^="_systemfield"], form input, form textarea', timeout=15000
            )
        except Exception:
            pass
        fields = await self.page.evaluate(
            """() => [...document.querySelectorAll('input:not([type=hidden]), textarea, select')].map(el => ({
                tag: el.tagName.toLowerCase(), type: el.type || '', name: el.name || ''
            }))"""
        )
        return {"fields": fields, "ats": "ashby"}

    async def navigate(self) -> bool:
        """Click 'Apply' si estamos en la landing del posting."""
        if "ashbyhq.com" not in self.page.url:
            return False
        # Form ya visible?
        try:
            el = await self.page.wait_for_selector(
                'input[name^="_systemfield"], form textarea', state="visible", timeout=2500
            )
            if el:
                return True
        except Exception:
            pass
        for sel in ['a:has-text("Apply for this Job")', 'button:has-text("Apply")', 'a:has-text("Apply")']:
            try:
                btn = await self.page.wait_for_selector(sel, state="visible", timeout=2500)
                if btn:
                    await btn.click()
                    await self.page.wait_for_timeout(3000)
                    return True
            except Exception:
                continue
        return True

    async def fill(self) -> FillResult:
        """Llena el form de Ashby."""
        self.filled = {}
        self.errors = []
        self.broken = []

        try:
            await self.page.wait_for_selector(
                'input[name^="_systemfield"], input, textarea, select',
                state="visible", timeout=10000,
            )
        except Exception:
            self.broken.append("form-not-visible")
        await self._dismiss_cookie_banner()

        # 1. CV PRIMERO: el "Autofill from resume" de Ashby re-procesa los
        #    campos al subir el CV y puede limpiar lo ya llenado.
        cv_path = self.candidate_data.get("cv_path", "")
        if cv_path:
            await self._upload_cv_ashby(cv_path)
            # Esperar a que el autofill de Ashby termine de procesar
            try:
                await self.page.wait_for_selector(
                    'text=Autofill completed', timeout=15000
                )
                await self.page.wait_for_timeout(1000)
            except Exception:
                await self.page.wait_for_timeout(3000)

        # 2. Campos de sistema de Ashby (después del autofill, ganan los nuestros)
        full_name = (
            f"{self.candidate_data.get('first_name', '')} "
            f"{self.candidate_data.get('last_name', '')}"
        ).strip()
        system_fields = [
            ('input[name="_systemfield_name"]', full_name, "full_name"),
            ('input[name="_systemfield_email"]', self.candidate_data.get("email", ""), "email"),
            ('input[name="_systemfield_phone"]', self.candidate_data.get("phone", ""), "phone"),
            ('input[name="_systemfield_linkedin"]', self.candidate_data.get("linkedin", ""), "linkedin"),
            ('input[name="_systemfield_github"]', self.candidate_data.get("github", ""), "github"),
            ('input[name="_systemfield_portfolio"]', self.candidate_data.get("portfolio", ""), "portfolio"),
            ('input[name="_systemfield_location"]', self.candidate_data.get("location", ""), "location"),
        ]
        for sel, value, key in system_fields:
            if value and value.strip():
                # El autofill de Ashby re-monta los inputs cuando llega la
                # respuesta del parseo: puede haber inputs duplicados
                # (viejo detached + nuevo visible). Llenar SIEMPRE el visible.
                for attempt in range(4):
                    filled_now = await self._fill_visible_input(sel, value)
                    await self.page.wait_for_timeout(2000)
                    current = await self._read_visible_input(sel)
                    if current == value.strip():
                        self.filled[key] = value
                        break
                    if not filled_now and not current and attempt >= 1:
                        break  # campo no existe en este form

        # 3. Custom questions (labels UUID + radios + selects) - helpers de Lever
        await self._answer_custom_questions()

        # 4. Pass2: required visibles vacíos → resolver por label
        await self._fill_missing_by_label(final_pass=True)

        # 5. Multi-step: algunos boards Ashby tienen Continue
        for _ in range(5):
            next_btn = await self._find_continue_button()
            if not next_btn:
                break
            logger.info("Ashby: avanzando página del form")
            await next_btn.click()
            await self.page.wait_for_timeout(2500)
            await self._answer_custom_questions()
            await self._fill_missing_by_label(final_pass=True)

        return FillResult(
            success=len(self.errors) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )

    async def _fill_visible_input(self, selector: str, value: str) -> bool:
        """Llena el input VISIBLE que matchee el selector (evita detached
        duplicados tras re-render del autofill)."""
        try:
            inputs = await self.page.query_selector_all(selector)
        except Exception:
            return False
        for el in inputs:
            try:
                if not await el.is_visible():
                    continue
                await el.fill(value)
                return True
            except Exception:
                continue
        return False

    async def _read_visible_input(self, selector: str) -> str:
        """Lee el valor del input visible."""
        try:
            inputs = await self.page.query_selector_all(selector)
            for el in inputs:
                if await el.is_visible():
                    return (await el.input_value() or "").strip()
        except Exception:
            pass
        return ""

    async def _upload_cv_ashby(self, cv_path: str):
        """Sube CV al input file de Ashby."""
        selectors = [
            'input[type="file"][accept*="pdf"]',
            'form input[type="file"]',
            'input[type="file"]',
        ]
        for sel in selectors:
            try:
                el = await self.page.wait_for_selector(sel, timeout=2500)
                if el:
                    await el.set_input_files(cv_path)
                    await self.page.wait_for_timeout(2500)
                    # Ashby muestra el nombre del archivo en la card
                    fname = cv_path.split("/")[-1]
                    card = await self.page.query_selector(
                        '[class*="filename"], [class*="file-name"], [class*="uploaded"]'
                    )
                    shown = ((await card.inner_text()) if card else "") or fname
                    self.filled["resume"] = shown.strip()[:60] or fname
                    logger.info(f"Ashby: CV subido ({self.filled['resume']})")
                    return True
            except Exception:
                continue
        self.broken.append("cv-upload")
        return False

    def _get_value_for_label(self, label: str) -> Optional[str]:
        """Respuestas Ashby: reutiliza el mapeo de Lever + preguntas 'why'."""
        label_lower = label.lower().strip()
        cd = self.candidate_data

        # Respuestas configuradas primero
        qa = cd.get("question_answers") or {}
        for keyword, answer in sorted(qa.items(), key=lambda kv: len(str(kv[0])), reverse=True):
            if str(keyword).lower() in label_lower and answer:
                return str(answer)

        # Preguntas motivacionales: usar cover letter / summary del perfil
        if "why" in label_lower and ("railway" in label_lower or "company" in label_lower
                                     or "us" in label_lower or "role" in label_lower
                                     or "work" in label_lower or "join" in label_lower
                                     or "interested" in label_lower or "this position" in label_lower):
            return cd.get("why_answer") or cd.get("cover_letter", "") or None
        if "cover letter" in label_lower:
            return cd.get("cover_letter", "") or None
        if "additional" in label_lower and ("information" in label_lower or "comments" in label_lower):
            return cd.get("additional_info") or None

        # Resto del mapeo genérico de Lever
        return super()._get_value_for_label(label)

    async def _answer_custom_questions(self):
        """Preguntas custom Ashby: label + input/textarea/radio/select."""
        questions = await self.page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('form label, [class*="question"], [class*="field"]').forEach(l => {
                    const t = l.textContent.trim();
                    if (t && t.length > 3 && t.length < 300) out.push(t);
                });
                return [...new Set(out)];
            }"""
        )
        logger.info(f"Ashby: {len(questions)} labels detectados")

        # Textinputs y textareas sin name de sistema → por label del contenedor
        # NOTA: Ashby NO usa <form> (React SPA), así que NO restringir a form
        inputs = await self.page.query_selector_all(
            'textarea, input[type="text"]:not([name^="_systemfield"])'
        )
        for inp in inputs:
            try:
                if not await inp.is_visible():
                    continue
                if (await inp.input_value() or "").strip():
                    continue
                label_text = await self._label_for_input(inp)
                if not label_text:
                    continue
                answer = self._get_value_for_label(label_text)
                if answer:
                    await inp.fill(answer)
                    self.filled[f"label:{label_text[:50]}"] = answer
                    logger.info(f"Ashby: '{label_text[:40]}' llenado")
            except Exception as e:
                logger.warning(f"Ashby input error: {type(e).__name__}: {e}")

        # Radios y selects con la maquinaria de Lever.
        # Ashby agrupa en <fieldset> sin <form>; el label de la pregunta va en el
        # fieldset (texto de pregunta + opciones concatenadas).
        try:
            radios = await self.page.query_selector_all('input[type="radio"]')
            if radios:
                groups = {}
                for r in radios:
                    name = await r.get_attribute("name") or "unamed"
                    groups.setdefault(name, []).append(r)
                for name, group in groups.items():
                    already_checked = False
                    for r in group:
                        if await r.is_checked():
                            already_checked = True
                            break
                    if already_checked:
                        continue
                    label_text = await self._ashby_radio_group_label(group[0]) or name
                    answer = self._get_value_for_label(label_text)
                    if not answer:
                        # EEO / opt-out: marcar "Decline / prefer not" si existe
                        await self._pick_radio(group, ["prefer not", "decline", "do not"])
                        continue
                    picked = await self._pick_radio_smart(group, answer, label_text)
                    if picked:
                        self.filled[f"radio:{label_text[:50]}"] = answer
                        logger.info(f"Ashby: radio '{label_text[:40]}' -> {answer}")
        except Exception as e:
            logger.warning(f"Ashby radio error: {type(e).__name__}: {e}")

    async def _radio_option_text(self, r) -> str:
        """Texto de la opción radio Ashby (sin <label>: leer div._option)."""
        generic = await super()._radio_option_text(r)
        if generic and generic != "on":
            return generic
        try:
            txt = await r.evaluate(
                """el => {
                    const opt = el.closest('[class*="option"], [class*="answer"], [class*="radio"]');
                    if (!opt) return '';
                    let t = (opt.textContent || '').replace(/\\s+/g, ' ').trim();
                    const inputs = opt.querySelectorAll('input, select, textarea');
                    inputs.forEach(i => t = t.replace(i.value || '', ''));
                    return t;
                }"""
            )
            return (txt or "").strip()
        except Exception:
            return generic

    async def _ashby_radio_group_label(self, radio) -> Optional[str]:
        """Resuelve el texto de la pregunta de un grupo de radios Ashby.

        Estructura: input[radio] → div._option → fieldset._fieldEntry
        El fieldset contiene 'Pregunta' + todas las opciones concatenadas.
        Restamos los textos de las opciones para quedarnos con la pregunta.
        """
        try:
            info = await radio.evaluate(
                """el => {
                    // Subir hasta el fieldset/group contenedor
                    let cur = el;
                    for (let i = 0; i < 6 && cur; i++) {
                        cur = cur.parentElement;
                        if (!cur) break;
                        const tag = cur.tagName;
                        const cls = (cur.className || '').toString();
                        if (tag === 'FIELDSET' || cls.includes('fieldEntry')) {
                            const full = (cur.textContent || '').replace(/\\s+/g, ' ').trim();
                            // Opciones del grupo (texto de cada radio option)
                            const opts = [...cur.querySelectorAll('input[type="radio"]')].map(r => {
                                const c = r.closest('label, div');
                                return c ? (c.textContent || '').replace(/\\s+/g, ' ').trim() : (r.value || '');
                            });
                            let q = full;
                            for (const o of opts) q = q.replace(o, '');
                            return q.replace(/\\s+/g, ' ').trim() || full || null;
                        }
                    }
                    return null;
                }"""
            )
            return info
        except Exception as e:
            logger.warning(f"Ashby radio group label error: {e}")
            return None

    async def validate(self) -> FillResult:
        """Valida errores visibles y required vacíos."""
        self.errors = []
        self.broken = []
        for sel in ["[role='alert']", ".error", "[class*='error']"]:
            try:
                els = await self.page.query_selector_all(sel)
                for el in els:
                    if await el.is_visible():
                        text = ((await el.inner_text()) or "").strip()
                        if text and "thank" not in text.lower():
                            self.errors.append(text[:200])
            except Exception:
                pass
        return FillResult(
            success=len(self.errors) == 0 and len(self.broken) == 0,
            filled_fields=self.filled,
            validation_errors=self.errors,
            broken_fields=self.broken,
        )

    async def submit_application(self) -> FillResult:
        """Submit + verificación de confirmación Ashby."""
        pre = await self._verify_ashby_confirmation(quick=True)
        if pre.success:
            return pre

        # Re-verificación pre-submit: el re-mount del autofill puede haber
        # limpiado campos después de que los llenamos
        for round_num in range(2):
            await self._answer_custom_questions()
            await self._fill_missing_by_label(final_pass=False)
            await self.page.wait_for_timeout(2000)
        await self._fill_missing_by_label(final_pass=True)

        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self.page.wait_for_timeout(500)

        submit_selectors = [
            'button:has-text("Submit Application")',
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
        ]
        for attempt in range(2):
            clicked = False
            for sel in submit_selectors:
                try:
                    btn = await self.page.wait_for_selector(sel, state="visible", timeout=3000)
                    if btn:
                        await btn.click()
                        clicked = True
                        logger.info("Ashby: submit clicked")
                        break
                except Exception:
                    continue
            if not clicked:
                return FillResult(success=False, error_message="No Ashby submit button found")

            result = await self._verify_ashby_confirmation()
            if result.success:
                return result

            # ¿El server pidió correcciones? Parsear campo faltante, rellenar, reintentar
            try:
                body = (await self.page.inner_text("body", timeout=3000)).lower()
                if "needs corrections" in body or "missing entry" in body:
                    logger.warning("Ashby: form needs corrections - re-filling and retrying")
                    await self._answer_custom_questions()
                    await self._fill_missing_by_label(final_pass=True)
                    await self.page.wait_for_timeout(2500)
                    await self._fill_missing_by_label(final_pass=True)
                    continue  # reintentar submit
            except Exception:
                pass
            break

        return await self._verify_ashby_confirmation()

    async def _verify_ashby_confirmation(self, quick: bool = False) -> FillResult:
        """Verifica confirmación de Ashby."""
        import asyncio
        signals = [
            "application received",
            "thanks for applying",
            "thank you for applying",
            "your application has been",
            "application submitted",
            "application was successfully submitted",
            "successfully submitted",
            "we'll be in touch",
            "successfully applied",
            "thank you for your interest",
        ]
        spam_signals = [
            "flagged as possible spam",
            "we couldn't submit your application",
            "couldn't submit your application",
            "possible spam",
            "verify you are not a robot",
        ]
        if quick:
            try:
                body = (await self.page.inner_text("body", timeout=2000)).lower()
                if any(s in body for s in signals):
                    return FillResult(success=True, filled_fields=self.filled)
            except Exception:
                pass
            return FillResult(success=False, error_message="not submitted yet")

        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            url = self.page.url.lower()
            if any(p in url for p in ("/thanks", "/confirmation", "/success")):
                await self._screenshot("ashby_confirmation")
                return FillResult(success=True, filled_fields=self.filled)
            try:
                body = (await self.page.inner_text("body", timeout=3000)).lower()
                if any(s in body for s in signals):
                    await self._screenshot("ashby_confirmation")
                    return FillResult(success=True, filled_fields=self.filled)
                if any(s in body for s in spam_signals):
                    await self._screenshot("ashby_spam_blocked")
                    return FillResult(
                        success=False,
                        error_message="Ashby spam detection bloqueó el submit (flag anti-bot). Usar modo semi-auto / nueva sesión.",
                    )
            except Exception:
                pass
            await self.page.wait_for_timeout(1000)

        await self._screenshot("ashby_no_confirmation")
        return FillResult(
            success=False,
            error_message="No Ashby confirmation detected",
            filled_fields=self.filled,
        )
