"""Depura el submit de Ashby: llena el form y captura el estado tras click Submit."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from auto_apply.unified.fillers_ashby import AshbyFiller

JOB_URL = "https://jobs.ashbyhq.com/livekit/1355f64e-b394-4982-8de6-6fd3e6e8f30d/application"
CANDIDATE = {
    "first_name": "Oscar", "last_name": "Alfaro Porras",
    "email": "goliohs@o7outlet.com", "phone": "87833158",
    "linkedin": "https://linkedin.com/in/ozdevops", "github": "https://github.com/Goliohs",
    "portfolio": "https://services.o7team.us", "location": "Costa Rica",
    "visa_status": "No visa required for remote work", "notice_period": "Immediate",
    "salary_expectation": "Negotiable", "years_experience": "10+",
    "english_level": "Advanced", "why_answer": "Me encanta la infraestructura distribuida. Tengo un homelab con Kubernetes y GPUs corriendo vLLM.",
    "cover_letter": "Soy ingeniero DevOps con 10+ anios construyendo infraestructura distribuida y plataformas cloud-native.",
    "cv_path": "/home/Helios/job-hunter/cv.pdf",
}


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(JOB_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)

        filler = AshbyFiller(page, {"url": JOB_URL, "title": "T", "company": "LiveKit"}, CANDIDATE)

        result = await filler.fill()
        print(f"[debug] fill result: success={result.success} filled={len(result.filled_fields)} errors={result.validation_errors} broken={result.broken_fields}")

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(800)

        # Click submit
        clicked = False
        for sel in ['button:has-text("Submit Application")', 'button:has-text("Submit application")', 'button:has-text("Submit")']:
            try:
                btn = await page.wait_for_selector(sel, state="visible", timeout=3000)
                if btn:
                    await btn.click()
                    clicked = True
                    print(f"[debug] submit clicked: {sel}")
                    break
            except Exception:
                continue
        if not clicked:
            print("[debug] NO submit button found")
            await browser.close()
            return

        await page.wait_for_timeout(8000)

        # Capturar estado post-submit
        url = page.url
        body = ""
        try:
            body = (await page.inner_text("body", timeout=3000))[:2500]
        except Exception:
            pass
        print(f"\n[debug] URL post-submit: {url}")
        print(f"[debug] BODY (primeros 2500):\n{body}")

        # Errores visibles
        errs = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('[role="alert"], [class*="error"], [class*="warning"], [data-testid*="error"], .ashby-error').forEach(e => {
                if (e.offsetParent !== null) out.push((e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,120));
            });
            return out.slice(0, 10);
        }""")
        print(f"\n[debug] errores visibles: {errs}")

        await page.screenshot(path="/tmp/ashby_submit_debug.png", full_page=False)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())