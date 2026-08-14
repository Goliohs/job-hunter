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
from pathlib import Path
from typing import Optional

# Load .env file
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from db.store import init_db, save_job, update_match, get_stats, get_top_jobs, log_run, get_jobs_for_apply
from aggregator import remotive, remoteok, wwr, hn, ats_career, company_career, lever
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

    # Get jobs to apply
    threshold = config["filter"]["high_match_threshold"]
    max_apply = config["auto_apply"].get("max_per_day", 5)
    jobs = get_jobs_for_apply(min_score=threshold, limit=max_apply * 3)  # Get more, filter by ATS

    if not jobs:
        print(f"No hay jobs con match >= {threshold} para aplicar")
        return

    # Filtrar solo jobs con ATS soportado
    supported_ats = {"lever", "greenhouse", "ashby"}
    jobs_to_apply = [j for j in jobs if auto_apply.detect_ats(j["url"]) in supported_ats]

    if not jobs_to_apply:
        print(f"No hay jobs con ATS soportado (Lever/Greenhouse/Ashby) entre los high matches")
        print("  Jobs encontrados pero con ATS no soportado:")
        for j in jobs:
            ats = auto_apply.detect_ats(j["url"])
            print(f"    {j['title']} @ {j['company']} -> {ats or 'unknown'}")
        return

    print(f"\n{'='*60}")
    print(f"  AUTO-APPLY: {len(jobs)} jobs (score >= {threshold})")
    print(f"{'='*60}")

    applied = 0
    for job in jobs:
        print(f"\n  Applying to: {job['title']} @ {job['company']} ({job['url']})")

        # Generate personalized cover letter for this job
        print(f"  📝 Generando cover letter personalizada...")
        cl_result = generate_cover_letter(job, profile)
        if cl_result:
            personalized_cover = cl_result.get("cover_letter", "")
            candidate["cover_letter"] = personalized_cover
            print(f"  ✓ Cover letter generada ({len(personalized_cover)} chars)")
        else:
            print(f"  ⚠ Usando cover letter base")

        result = auto_apply.auto_apply_job(job, candidate, cv_path, headless=True)

        if result.get("success"):
            print(f"  ✓ Applied via {result.get('ats', 'unknown')}")
            applied += 1
        else:
            print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")

    print(f"\n  Applied: {applied}/{len(jobs)}")
    print_stats(config)


def run_semi_apply(config: dict, job_id: Optional[int] = None):
    """Aplicación semi-auto: llena el form automáticamente, humano resuelve CAPTCHA."""
    from auto_apply.semi_auto import semi_apply_job, build_candidate_from_config, ensure_xvfb_running
    from db.store import get_job
    from generator import generate_application_package, generate_application_pdfs, load_base_cv

    init_db()
    profile = config["profile"]

    # Asegurar Xvfb corriendo
    if not ensure_xvfb_running(":99"):
        return
    os.environ.setdefault("DISPLAY", ":99")

    def _prepare_and_apply(job: dict) -> dict:
        """Para un job: genera PDFs + candidate + aplica semi-auto."""
        print(f"\n  Generando PDFs para {job['company']}...")
        package = generate_application_package(job, profile)
        pdfs = generate_application_pdfs(job, package, profile)
        cv_pdf = pdfs.get("cv_pdf") or "/home/Helios/job-hunter/cv.txt"
        cl_pdf = pdfs.get("cover_letter_pdf")
        print(f"  CV:  {cv_pdf}")
        print(f"  CL:  {cl_pdf}")

        candidate = build_candidate_from_config(config, cv_pdf, cl_pdf)
        return semi_apply_job(job, candidate, timeout=600)

    # Modo individual: un solo job
    if job_id is not None:
        job = get_job(job_id)
        if not job:
            print(f"No se encontró job con id={job_id}")
            return
        result = _prepare_and_apply(job)
        print(result)
        return

    # Modo batch: recorrer todos los high-match con ATS soportado
    from db.store import get_jobs_for_apply
    from auto_apply.ats_detector import detect_ats, ATSType

    threshold = config["filter"]["high_match_threshold"]
    max_apply = config["auto_apply"].get("max_per_day", 5)
    jobs = get_jobs_for_apply(min_score=threshold, limit=max_apply * 3)

    if not jobs:
        print(f"No hay jobs con match >= {threshold} para aplicar")
        return

    # Filtrar por ATS soportado
    ats_supported = {ATSType.LEVER.value, ATSType.GREENHOUSE.value, ATSType.ASHBY.value}
    jobs_to_apply = []
    for j in jobs:
        ats = detect_ats(j["url"])
        ats_val = ats.value if ats else None
        if ats_val in ats_supported:
            jobs_to_apply.append(j)

    if not jobs_to_apply:
        print(f"No hay jobs con ATS soportado entre los {len(jobs)} high matches")
        print("  (Sólo Lever/Greenhouse/Ashby soportan semi-auto)")
        for j in jobs:
            ats = detect_ats(j["url"])
            print(f"    {j['title']} @ {j['company']} -> {ats.value if ats else 'unknown ATS'}")
        return

    print(f"\n{'='*60}")
    print(f"  SEMI-AUTO APPLY: {len(jobs_to_apply)} jobs (score >= {threshold})")
    print(f"  Presiona Ctrl+C entre jobs si quieres parar")
    print(f"{'='*60}")

    applied = 0
    for i, job in enumerate(jobs_to_apply, 1):
        print(f"\n--- Job {i}/{len(jobs_to_apply)} ---")
        print(f"  {job['title']} @ {job['company']}")
        print(f"  Score: {job.get('match_score', 'N/A')}")

        result = _prepare_and_apply(job)
        if result.get("success"):
            applied += 1

        # Pausa entre jobs
        if i < len(jobs_to_apply):
            print("\n  Presiona Enter para el siguiente job, o Ctrl+C para parar...")
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                print("\n  Saliendo del modo batch...")
                break

    print(f"\n  Resultado: {applied}/{len(jobs_to_apply)} aplicaciones enviadas")
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
