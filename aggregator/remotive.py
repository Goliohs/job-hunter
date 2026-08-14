"""Scraper para Remotive.io (API JSON pública, cero riesgo)"""
import httpx
from typing import Optional


def fetch(config: dict) -> list[dict]:
    """Devuelve lista de jobs normalizados."""
    url = config["url"]
    categories = config.get("categories", [])

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[remotive] Error: {e}")
        return []

    jobs_raw = data.get("jobs", [])
    print(f"[remotive] Fetched {len(jobs_raw)} jobs from API")

    jobs = []
    for j in jobs_raw:
        # Filtrar por categoría si está configurado
        if categories:
            cat = j.get("category", "").lower().replace(" ", "-")
            if cat not in categories:
                continue

        jobs.append(
            {
                "source": "remotive",
                "external_id": str(j.get("id", "")),
                "title": j.get("title", "").strip(),
                "company": j.get("company_name", "").strip(),
                "description": j.get("description", "")[:5000],  # truncate
                "url": j.get("url", ""),
                "location": j.get("candidate_required_location", ""),
                "remote": True,
                "tags": j.get("tags", []),
                "salary": j.get("salary", ""),
                "posted_date": j.get("publication_date", ""),
            }
        )

    return jobs
