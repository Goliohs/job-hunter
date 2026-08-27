"""
Punto de entrada unificado para auto-apply (integra con job-hunter existente).
"""
import asyncio
import sys
import os
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

# Asegurar que job-hunter está en path
sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_apply.unified.orchestrator import apply_to_job, ApplicationOrchestrator
from auto_apply.unified.session import BrowserSessionManager
from auto_apply.unified.notifications import NotificationManager
from auto_apply.unified.account import AccountManager
from auto_apply import detect_ats
from auto_apply.unified.fillers import FILLER_REGISTRY
from db.store import init_db, get_jobs_for_apply, get_job, update_job
from job_data import job_folder_manager

# Cargar configuración
import yaml
with open("/home/Helios/job-hunter/config.yaml") as f:
    CONFIG = yaml.safe_load(f)


async def run_auto_apply_unified(
    min_score: int = 70,
    max_applications: int = 5,
    semi_auto: bool = True,
    headless: bool = False,
    job_id: int = None,
):
    """
    Ejecuta auto-apply unificado.
    
    Args:
        min_score: Score mínimo para aplicar
        max_applications: Máximo aplicaciones por corrida
        semi_auto: Si True, espera aprobación humana
        headless: Si True, browser headless
        job_id: ID específico de job (None = todos los elegibles)
    """
    init_db()
    
    # Perfil del candidato (desde config.yaml del usuario)
    profile = CONFIG["profile"]

    # Credenciales desde auto_apply/credentials.py (gitignoreado - ver credentials.py.example)
    try:
        from auto_apply.credentials import ZOHO_EMAIL, ZOHO_APP_PASSWORD, LINKEDIN_COOKIES
    except ImportError:
        print("⚠ auto_apply/credentials.py no encontrado.")
        print("  Copia credentials.py.example y llena tus credenciales para Zoho/LinkedIn.")
        ZOHO_EMAIL = ZOHO_APP_PASSWORD = None
        LINKEDIN_COOKIES = {}

    candidate_data = {
        "first_name": profile.get("first_name", ""),
        "last_name": profile.get("last_name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "linkedin": profile.get("linkedin", ""),
        "github": profile.get("github", ""),
        "portfolio": profile.get("portfolio", ""),
        "location": profile.get("location", ""),
        "visa_status": profile.get("visa_status", "No visa required for remote work"),
        "notice_period": profile.get("notice_period", "Immediate"),
        "salary_expectation": profile.get("salary_expectation", "Negotiable"),
        "question_answers": profile.get("question_answers", {}),
        "english_level": profile.get("english_level", "Advanced"),
        "years_experience": str(profile.get("years_experience", 5)) + "+",
        "current_company": profile.get("current_company", ""),
        "how_heard_answer": profile.get("how_heard_answer", "Job posting"),
        "cover_letter": profile.get("cover_letter", ""),
        "why_answer": profile.get("why_answer", ""),
        "cv_path": str(Path(__file__).parent.parent / "cv.md"),
        "cover_letter_path": profile.get("cover_letter_path", ""),
        # Credenciales (opcional - para verificación por email y Easy Apply)
        "zoho_email": ZOHO_EMAIL,
        "zoho_app_password": ZOHO_APP_PASSWORD,
        "linkedin_cookies": LINKEDIN_COOKIES,
    }
    
    # Obtener jobs para aplicar
    if job_id:
        jobs = [get_job(job_id)]
        jobs = [j for j in jobs if j]
    else:
        jobs = get_jobs_for_apply(min_score=min_score, limit=max_applications * 3)
    
    # Filtrar solo jobs con ATS soportado
    supported_ats = set(FILLER_REGISTRY.keys())
    ats_jobs = []
    for job in jobs:
        ats = detect_ats(job["url"])
        if ats and ats in supported_ats:
            ats_jobs.append(job)
    
    ats_jobs = ats_jobs[:max_applications]
    
    if not ats_jobs:
        print("No hay jobs con ATS soportado para aplicar")
        return
    
    # Configuración para apply_to_job
    config = {
        "ats_credentials": CONFIG.get("ats_credentials", {}),
        "ntfy": CONFIG.get("ntfy", {}),
        "email": CONFIG.get("email", {}),
    }
    
    print(f"\n{'='*60}")
    print(f"  UNIFIED AUTO-APPLY: {len(ats_jobs)} jobs")
    print(f"  Semi-auto: {semi_auto}")
    print(f"{'='*60}\n")
    
    applied = 0
    for i, job in enumerate(ats_jobs, 1):
        print(f"\n--- Job {i}/{len(ats_jobs)} ---")
        print(f"  {job['title']} @ {job['company']}")
        print(f"  Score: {job.get('match_score', 'N/A')}")
        print(f"  ATS: {detect_ats(job['url'])}")
        print(f"  URL: {job['url']}")
        
        try:
            # Generar CV PDF adaptado a este job (reemplaza cv.txt)
            job_candidate = dict(candidate_data)
            try:
                from cv_generator import generate_job_cv
                from pathlib import Path as _P
                job_folder = _P(job_folder_manager.create_job_folder(job).folder)
                cv_pdf = generate_job_cv(job, output_dir=job_folder)
                job_candidate["cv_path"] = cv_pdf
                print(f"  📄 CV adaptado: {cv_pdf}")
            except Exception as cv_err:
                print(f"  ⚠ CV generation failed ({cv_err}), usando cv.txt")
            
            state = await apply_to_job(
                job_data=job,
                candidate_data=job_candidate,
                semi_auto=semi_auto,
                headless=headless,
                config=config,
            )
            
            if state.success:
                print(f"  ✅ SUCCESS: {state.submit_response}")
                applied += 1
                # Actualizar DB
                update_job(job["id"], "applied", f"Applied via unified auto-apply: {state.submit_response}")
            elif state.status.value == "parked":
                print(f"  ⏸ PARKED: {state.error_message}")
                # Marcar como parked para que el batch pase a jobs nuevos.
                # Disponible para reintento manual con --job-id.
                update_job(job["id"], "parked", f"Parked (requiere humano): {state.error_message}")
            else:
                print(f"  ❌ FAILED: {state.error_message}")
                update_job(job["id"], "failed", f"Apply failed: {state.error_message}")
                
        except Exception as e:
            print(f"  ❌ ERROR: {e}")
        
        # Pausa entre aplicaciones
        if i < len(ats_jobs):
            print("\n  Pausa 5s antes del siguiente...")
            await asyncio.sleep(5)
    
    print(f"\n{'='*60}")
    print(f"  RESULTADO: {applied}/{len(ats_jobs)} aplicaciones exitosas")
    print(f"{'='*60}\n")


def main():
    """Entry point para CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Auto-Apply")
    parser.add_argument("--score", type=int, default=70, help="Min score")
    parser.add_argument("--max", type=int, default=5, help="Max applications")
    parser.add_argument("--semi", action="store_true", default=False, help="Semi-auto mode (espera aprobación humana)")
    parser.add_argument("--headless", action="store_true", help="Headless browser")
    parser.add_argument("--job-id", type=int, help="Specific job ID")
    
    args = parser.parse_args()
    
    asyncio.run(run_auto_apply_unified(
        min_score=args.score,
        max_applications=args.max,
        semi_auto=args.semi,
        headless=args.headless,
        job_id=args.job_id,
    ))


if __name__ == "__main__":
    main()