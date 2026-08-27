"""Punto de entrada principal del Job Hunter Bot.

Uso:
    python3 main.py          # Corre agregador + filtro completo
    python3 main.py --stats  # Solo muestra estadísticas
    python3 main.py --top    # Muestra top 20 matches
    python3 main.py --scrape  # Solo scrapea, no filtra con LLM
    python3 main.py --apply  # Auto-aplica a matches >= 80
"""
import sys
import os
import time
import yaml
import asyncio
from pathlib import Path
from typing import Optional

# Load .env file
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from db.store import init_db, save_job, update_match, get_stats, get_top_jobs, log_run, get_jobs_for_apply
from aggregator import remotive, remoteok, wwr, hn, ats_career, company_career, lever, wellfound, yc_jobs, playwright_scraper
from aggregator.linkedin import fetch_all_linkedin_jobs
from aggregator.linkedin_easy_apply import fetch_linkedin_jobs
from aggregator.standard_ats import fetch_all_standard_ats_jobs
from filter.matcher import filter_job
from alerts.telegram import alert_high_match
import auto_apply
from generator import generate_cover_letter, adapt_cv, load_base_cv


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    # Devuelve el config completo, no solo profile
    return cfg


def run_aggregators(config: dict) -> dict:
    """Corre todos los scrapers habilitados. Devuelve {source: [jobs]}."""
    sources = config.get("sources", {})
    all_results = {}

    if sources.get("remotive", {}).get("enabled"):
        jobs = remotive.fetch(sources["remotive"])
        all_results["remotive"] = jobs

    if sources.get("remoteok", {}).get("enabled"):
        jobs = remoteok.fetch(sources["remoteok"])
        all_results["remoteok"] = jobs

    if sources.get("weworkremotely", {}).get("enabled"):
        jobs = wwr.fetch(sources["weworkremotely"])
        all_results["wwr"] = jobs

    if sources.get("hackernews", {}).get("enabled"):
        jobs = hn.fetch(sources["hackernews"])
        all_results["hackernews"] = jobs

    # ATS Career Pages (Lever/Greenhouse/Ashby company pages)
    if sources.get("ats_career_pages", {}).get("enabled"):
        jobs = ats_career.fetch(sources["ats_career_pages"])
        # ats_career returns flat list, we need to group by source
        grouped = {}
        for job in jobs:
            src = job.get("source", "ats_career")
            if src not in grouped:
                grouped[src] = []
            grouped[src].append(job)
        all_results.update(grouped)

    # Lever career pages
    if sources.get("lever", {}).get("enabled"):
        jobs = lever.fetch(sources["lever"])
        all_results["lever"] = jobs

    # Company career pages
    if sources.get("company_career_pages", {}).get("enabled"):
        jobs = company_career.fetch(sources["company_career_pages"])
        all_results["company_career"] = jobs

    # LinkedIn
    if sources.get("linkedin", {}).get("enabled"):
        jobs = fetch_all_linkedin_jobs(sources)
        for search_name, job_list in jobs.items():
            all_results[f"linkedin_{search_name}"] = job_list

    # Wellfound (AngelList)
    if sources.get("wellfound", {}).get("enabled"):
        jobs = wellfound.fetch(sources)
        all_results["wellfound"] = jobs

    # YC Job Board
    if sources.get("yc_jobs", {}).get("enabled"):
        jobs = yc_jobs.fetch(sources)
        all_results["yc_jobs"] = jobs

    # LinkedIn Easy Apply
    if sources.get("linkedin_easy_apply", {}).get("enabled"):
        print("[linkedin_easy_apply] Fetching jobs...")
        try:
            jobs = asyncio.run(fetch_linkedin_jobs(
                keywords=sources["linkedin_easy_apply"].get("keywords", ["devops", "site reliability", "platform engineer", "kubernetes", "python", "golang"]),
                location=sources["linkedin_easy_apply"].get("location", "Remote"),
                max_pages=sources["linkedin_easy_apply"].get("max_pages", 3),
                easy_apply_only=True,
            ))
            all_results["linkedin_easy_apply"] = jobs
            print(f"  [linkedin_easy_apply] {len(jobs)} jobs")
        except Exception as e:
            print(f"  [linkedin_easy_apply] Error: {e}")

    # Standard ATS platforms (Workable, Recruitee, Teamtailor, BreezyHR)
    if sources.get("standard_ats", {}).get("enabled"):
        print("[standard_ats] Fetching jobs from Workable/Recruitee/Teamtailor...")
        jobs = asyncio.run(fetch_all_standard_ats_jobs(
            keywords=sources["standard_ats"].get("keywords", ["devops", "kubernetes", "python", "golang", "sre"]),
            location=sources["standard_ats"].get("location", "Remote"),
        ))
        all_results["standard_ats"] = jobs
        print(f"  [standard_ats] {len(jobs)} jobs")

    # Playwright-based scrapers (Wellfound, YC Jobs - more reliable)
    if sources.get("wellfound", {}).get("enabled"):
        print("[playwright] Fetching Wellfound jobs...")
        jobs = playwright_scraper.fetch_wellfound_jobs(sources["wellfound"].get("max_pages", 3))
        all_results["wellfound_pw"] = jobs

    if sources.get("yc_jobs", {}).get("enabled"):
        print("[playwright] Fetching YC Jobs...")
        jobs = playwright_scraper.fetch_yc_jobs(sources["yc_jobs"].get("max_pages", 3))
        all_results["yc_jobs_pw"] = jobs

    return all_results


def run_pipeline(config: dict):
    """Pipeline completo: scrapea → guarda → filtra con LLM."""
    init_db()
    profile = config["profile"]

    print("\n" + "=" * 60)
    print("  JOB HUNTER BOT - Iniciando pipeline")
    print("=" * 60)

    # 1. Scrapear fuentes
    print("\n[1/3] Scrapeando fuentes públicas...")
    all_jobs = run_aggregators(config)

    # 2. Guardar en DB (dedupe automático)
    print("\n[2/3] Guardando jobs en DB...")
    total_saved = 0
    total_dup = 0
    for source, jobs in all_jobs.items():
        print(f"  {source}: {len(jobs)} jobs encontrados")
        saved = 0
        for job in jobs:
            if save_job(job):
                saved += 1
        total_saved += saved
        total_dup += len(jobs) - saved
        log_run(source, len(jobs), saved, len(jobs) - saved)
        print(f"    → {saved} nuevos, {len(jobs) - saved} duplicados")

    print(f"\n  Total nuevos guardados: {total_saved}")
    print(f"  Total duplicados (ignorados): {total_dup}")

    # 3. Filtrar con LLM solo los nuevos
    if not os.environ.get("NIM_API_KEY"):
        print("\n[3/3] NIM_API_KEY no configurada — saltando filtro LLM")
        print("       Configura con: export NIM_API_KEY='tu_api_key'")
        print_stats()
        return

    print("\n[3/3] Filtrando con NIM LLM...")
    from db.store import get_unmatched_jobs
    unmatched = get_unmatched_jobs(limit=config["filter"]["max_jobs_per_run"])
    print(f"  Analizando {len(unmatched)} jobs sin scoring...")

    matched = 0
    rejected = 0
    high_match = 0
    threshold = config["filter"]["min_score"]
    high_threshold = config["filter"]["high_match_threshold"]

    for i, job in enumerate(unmatched, 1):
        result = filter_job(job, profile, config)

        if result.get("saved"):
            update_match(
                job["source"],
                job["external_id"],
                result["match_score"],
                result["reason"],
            )
            matched += 1
            if result["match_score"] >= high_threshold:
                high_match += 1
                print(f"\n  *** HIGH MATCH ({result['match_score']}) ***")
                print(f"  {job['title']} @ {job['company']}")
                print(f"  {job['url']}")
                print(f"  {result['reason']}\n")
                # Alerta Telegram si está configurada
                alert_high_match(job, result, config)
        elif result.get("rejected"):
            update_match(
                job["source"],
                job["external_id"],
                result.get("match_score", 0),
                result.get("reject_reason", ""),
                result.get("reject_reason", ""),
            )
            rejected += 1

        # Progress cada 10
        if i % 10 == 0:
            print(f"  ...procesados {i}/{len(unmatched)}")

        # Rate limit suave para NIM
        time.sleep(2.0)

    print(f"\n  Resultados del filtro LLM:")
    print(f"  Matched (>= {threshold}): {matched}")
    print(f"  High match (>= {high_threshold}): {high_match}")
    print(f"  Rejected: {rejected}")

    print_stats(config)


def print_stats(config=None):
    stats = get_stats()
    high_threshold = config.get("filter", {}).get("high_match_threshold", 80) if config else 80
    print("\n" + "=" * 60)
    print("  ESTADÍSTICAS DATABASE")
    print("=" * 60)
    print(f"  Total jobs en DB:    {stats['total']}")
    print(f"  Matched (>= 60):     {stats['matched']}")
    print(f"  High match (>= {high_threshold}):  {stats['high_match']}")
    print(f"  Aplicados:           {stats['applied']}")
    print("=" * 60 + "\n")


def print_top():
    """Muestra top 20 matches."""
    init_db()
    jobs = get_top_jobs(limit=20)
    if not jobs:
        print("No hay jobs con match >= 60 todavía. Corre: python3 main.py")
        return

    print("\n" + "=" * 60)
    print("  TOP 20 JOB MATCHES")
    print("=" * 60)
    for i, job in enumerate(jobs, 1):
        print(f"\n  {i}. [{job['match_score']}] {job['title']}")
        print(f"     Company: {job['company']}")
        print(f"     URL: {job['url']}")
        print(f"     Reason: {job.get('match_reason', 'N/A')[:120]}")
    print("\n" + "=" * 60 + "\n")


def run_auto_apply(config: dict):
    """Auto-aplica a jobs con high match (>= threshold)."""
    init_db()
    profile = config["profile"]

    # Build CandidateProfile
    cv_path = os.environ.get("CV_PATH", "/home/Helios/job-hunter/cv.pdf")
    if not os.path.exists(cv_path):
        cv_path = "/home/Helios/job-hunter/cv.txt"
        if not os.path.exists(cv_path):
            print(f"ERROR: CV no encontrado en {cv_path}")
            return

    candidate = {
        "first_name": profile.get("first_name", "Oscar"),
        "last_name": profile.get("last_name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "github": profile.get("github", ""),
        "portfolio": profile.get("portfolio", ""),
        "cover_letter": profile.get("cover_letter", ""),
        "visa_status": profile.get("visa_status", "No visa required for remote work"),
        "notice_period": profile.get("notice_period", "Immediate"),
        "salary_expectation": profile.get("salary_expectation", "Negotiable"),
    }

    # Get jobs to apply - prioritize supported ATS jobs
    threshold = config["filter"]["high_match_threshold"]
    max_apply = config["auto_apply"].get("max_per_day", 5)
    
    # Usar auto-apply unificado
    from auto_apply.unified_main import run_auto_apply_unified
    
    # Run unified auto-apply (async)
    import asyncio
    # Headed por defecto (anti-bot): corre bajo Xvfb vía cron_runner.sh.
    # En headless Ashby flaggea como spam.
    headless = os.environ.get("APPLY_HEADLESS", "0") == "1"
    asyncio.run(run_auto_apply_unified(
        min_score=threshold,
        max_applications=max_apply,
        semi_auto=False,  # Fully automatic
        headless=headless,
    ))
    print_stats(config)
    return


def run_semi_apply(config: dict, job_id: Optional[int] = None):
    """Aplicación semi-auto unificada: llena form, humano resuelve CAPTCHA y hace submit."""
    import asyncio
    from auto_apply.unified_main import run_auto_apply_unified
    
    asyncio.run(run_auto_apply_unified(
        min_score=config["filter"]["high_match_threshold"],
        max_applications=config["auto_apply"].get("max_per_day", 5),
        semi_auto=True,
        headless=False,  # Headed para semi-auto
        job_id=job_id,
    ))
    print_stats(config)


def main():
    config = load_config()

    if "--stats" in sys.argv:
        print_stats()
    elif "--top" in sys.argv:
        print_top()
    elif "--scrape" in sys.argv:
        # Solo scrapea, sin LLM
        os.environ.pop("NIM_API_KEY", None)
        run_pipeline(config)
    elif "--semi-apply" in sys.argv:
        # Job_id opcional como segundo argumento
        job_id = None
        idx = sys.argv.index("--semi-apply")
        if idx + 1 < len(sys.argv):
            try:
                job_id = int(sys.argv[idx + 1])
            except ValueError:
                pass
        run_semi_apply(config, job_id)
    elif "--apply" in sys.argv:
        run_auto_apply(config)
    else:
        run_pipeline(config)


if __name__ == "__main__":
    main()
