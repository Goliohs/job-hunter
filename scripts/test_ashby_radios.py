"""Test interactivo del AshbyFiller._answer_custom_questions contra la página LiveKit."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from auto_apply.unified.fillers_ashby import AshbyFiller

JOB_URL = "https://jobs.ashbyhq.com/livekit/1355f64e-b394-4982-8de6-6fd3e6e8f30d/application"

CANDIDATE = {
    "first_name": "YourName", "last_name": "",
    "email": "your@email.com", "phone": "0000000",
    "linkedin": "https://linkedin.com/in/youruser", "github": "https://github.com/yourgithub",
    "portfolio": "https://your-portfolio.example.com", "location": "Your Country",
    "visa_status": "No visa required for remote work", "notice_period": "Immediate",
    "salary_expectation": "Negotiable", "years_experience": "10+",
    "english_level": "Advanced", "why_answer": "Me encanta la infraestructura distribuida...",
    "cover_letter": "Soy ingeniero DevOps con 10+ años...", "cv_path": str(Path(__file__).resolve().parent.parent / "cv.pdf"),
}


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(JOB_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)

        filler = AshbyFiller(page, {"url": JOB_URL, "title": "T", "company": "LiveKit"}, CANDIDATE)

        # Subir CV primero (como hace fill) para que Ashby renderice radios
        try:
            await filler._upload_cv_ashby(CANDIDATE["cv_path"])
        except Exception as e:
            print(f"[test] CV upload error: {e}")
        await page.wait_for_timeout(6000)

        # Ejecutar respuesta de preguntas custom
        await filler._answer_custom_questions()

        # Reportar estado de radios
        state = await page.evaluate("""() => {
            const groups = {};
            document.querySelectorAll('input[type="radio"]').forEach(r => {
                const n = r.name || 'unnamed';
                (groups[n] = groups[n] || []).push({ checked: r.checked, label: (r.closest('div[class*="option"]')||{}).textContent ? r.closest('div[class*="option"]').textContent.trim().slice(0,30) : r.value });
            });
            const out = [];
            for (const [n, g] of Object.entries(groups)) {
                const checked = g.filter(x => x.checked).map(x => x.label);
                const q = (g.length + ' options');
                out.push({ name: n.slice(0,30), q, checked });
            }
            return out;
        }""")
        for s in state:
            print(f"  {s['name']:<30} {s['q']:<12} checked={s['checked']}")
        print("\nfilled:", dict(list(filler.filled.items())[:12]))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())