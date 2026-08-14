"""CLI helper para generar paquetes de aplicación (cover letter + CV adaptado) para jobs específicos."""
import sys
import os
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generator import generate_application_package, save_application_files, load_base_cv
from db.store import init_db, get_conn


def main():
    if len(sys.argv) < 2:
        print("Uso: python3 generate_app.py <job_id> [--save]")
        print("       python3 generate_app.py --top 5")
        return

    init_db()
    conn = get_conn()

    with open("/home/Helios/job-hunter/config.yaml") as f:
        config = yaml.safe_load(f)

    profile = config["profile"]

    if sys.argv[1] == "--top":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        jobs = conn.execute(
            "SELECT id, match_score, title, company, url FROM jobs WHERE match_score >= 80 AND status='new' ORDER BY match_score DESC LIMIT ?",
            (limit,)
        ).fetchall()
        
        print(f"Top {limit} jobs para generar aplicación:")
        for j in jobs:
            print(f"  [{j['id']}] [{j['match_score']}] {j['title']} @ {j['company']}")
        return

    job_id = int(sys.argv[1])
    job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    
    if not job:
        print(f"Job {job_id} no encontrado")
        return

    job = dict(job)
    print(f"Generando aplicación para: [{job['match_score']}] {job['title']} @ {job['company']}")
    print(f"URL: {job['url']}")

    package = generate_application_package(job, profile)

    if not package.get("cover_letter") and not package.get("adapted_cv"):
        print("ERROR: No se pudo generar el paquete")
        return

    print(f"\n=== COVER LETTER ===")
    print(f"Subject: {package.get('subject_line', '')}")
    print(f"Key points: {package.get('key_match_points', [])}")
    print(f"\n{package.get('cover_letter', 'N/A')}")

    print(f"\n=== ADAPTED CV (summary) ===")
    print(f"Changes: {package.get('cv_changes_summary', '')}")
    cv_preview = package.get('adapted_cv', '')[:500]
    print(f"{cv_preview}...")

    if "--save" in sys.argv:
        files = save_application_files(job, package)
        print(f"\nArchivos guardados:")
        for k, v in files.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()