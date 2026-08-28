"""Trace de ambos grupos 2-radio (authorized + sponsorship)."""
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

        radios = await page.query_selector_all('input[type="radio"]')
        names = {}
        for r in radios:
            nm = await r.get_attribute("name")
            names.setdefault(nm, []).append(r)

        for nm, grp in names.items():
            if len(grp) != 2:
                continue
            label = await filler._ashby_radio_group_label(grp[0])
            answer = filler._get_value_for_label(label)
            print(f"\n=== grupo: label={label!r}")
            print(f"    answer={answer!r}")
            ot = [await filler._radio_option_text(r) for r in grp]
            print(f"    option_texts={ot!r}")
            n = [filler._norm(t) for t in ot]
            print(f"    normed={n!r}  ans_norm={filler._norm(answer)!r}")
            # simular direct match
            ans = filler._norm(answer)
            for i, nv in enumerate(n):
                if nv and (nv == ans or ans in nv or (len(ans) > 3 and nv in ans)):
                    print(f"    DIRECT MATCH radio[{i}]")
            checked_before = [await r.is_checked() for r in grp]
            picked = await filler._pick_radio_smart(grp, answer, label)
            checked_after = [await r.is_checked() for r in grp]
            print(f"    checked before={checked_before}  _pick_radio_smart={picked}  after={checked_after}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())