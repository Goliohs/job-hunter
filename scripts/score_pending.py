"""Scoring masivo de jobs pendientes (match_score=0) con el modelo LLM configurado."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from dotenv import load_dotenv
load_dotenv()

from db.store import get_conn, get_unmatched_jobs, update_match
from filter.matcher import filter_job

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
with open(CONFIG_PATH) as f:
    CONFIG = yaml.safe_load(f)


def main():
    import os
    import sys
    # --local: forzar Ollama local (sin NIM) para evitar rate limits
    if "--local" in sys.argv:
        os.environ.pop("NIM_API_KEY", None)
        print("[score] Modo LOCAL: usando Ollama (sin NIM)")

    if not os.environ.get("NIM_API_KEY"):
        print("[score] NIM_API_KEY no configurada — se usará Ollama local")

    profile = CONFIG["profile"]
    delay = float(CONFIG["filter"].get("rate_limit_seconds", 2.0))
    max_jobs = int(CONFIG["filter"].get("max_jobs_per_run", 5))

    # Single pass: procesar TODOS los unmatched en orden (get_unmatched_jobs
    # ordena por created_at DESC; snapshot completo evita que los jobs nuevos
    # que fallan bloqueen a los más viejos).
    processed = 0
    matched = rejected = failed = high = 0
    pending = get_unmatched_jobs(limit=100000)
    if not pending:
        print("[score] No hay jobs sin scorear")
        return
    for job in pending:
        result = filter_job(job, profile, CONFIG)
        if result.get("saved"):
            update_match(
                job["source"], job["external_id"],
                result["match_score"], result["reason"],
            )
            matched += 1
            if result["match_score"] >= CONFIG["filter"]["high_match_threshold"]:
                high += 1
                print(f"  HIGH {result['match_score']}: {job['title'][:60]} @ {job['company']}")
        elif result.get("rejected"):
            update_match(
                job["source"], job["external_id"],
                result.get("match_score", 0), result.get("reject_reason", ""),
            )
            rejected += 1
        else:
            failed += 1
        processed += 1
        print(f"  [{processed}] {job['title'][:50]:<50} -> {result.get('match_score', 'ERR')}")
        time.sleep(delay)

    print(f"\nScoring completado: {processed} procesados, {matched} matched, {rejected} rejected, {failed} fallos LLM, {high} high match")


if __name__ == "__main__":
    main()