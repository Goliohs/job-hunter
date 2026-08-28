"""Aggregator para Freelancer.com via API publica (sin autenticacion).

Freelancer.com expone una API REST publica que NO requiere login ni API key
para buscar proyectos activos. Es legal, documentada y no viola ToS.

Endpoint: https://www.freelancer.com/api/projects/0.1/projects/active/
Docs: https://developers.freelancer.com/docs

Estrategia anti-ban:
  - Solo usa API publica (sin login, sin scraping, sin browser automation)
  - Rate limit generoso entre requests
  - User-Agent honesto
  - NO auto-aplica. Solo alerta al humano para que aplique manualmente.
"""
import httpx
import time
import random
from typing import Optional

# Rate limit entre queries (segundos)
RATE_LIMIT_MIN = 3.0
RATE_LIMIT_MAX = 6.0

# API base
API_BASE = "https://www.freelancer.com/api/projects/0.1/projects/active/"


def _fetch_jobs(query: str, limit: int = 20, offset: int = 0) -> Optional[dict]:
    """Busca proyectos activos en Freelancer.com via API publica."""
    params = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "compact": 1,  # respuesta compacta
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; JobHunter/1.0; +https://github.com/youruser/job-hunter)",
        "Accept": "application/json",
    }

    try:
        resp = httpx.get(API_BASE, params=params, timeout=30, follow_redirects=True, headers=headers)
        if resp.status_code != 200:
            print(f"  [freelancer] HTTP {resp.status_code}")
            return None
        data = resp.json()
        if data.get("status") != "success":
            print(f"  [freelancer] API error: {data.get('status')}")
            return None
        return data
    except Exception as e:
        print(f"  [freelancer] Error: {e}")
        return None


def _parse_project(project: dict, search_query: str) -> dict:
    """Normaliza un proyecto de Freelancer.com al formato del job-hunter."""
    # Budget
    budget_info = project.get("budget", {})
    currency_info = project.get("currency", {})
    currency_code = currency_info.get("code", "USD")
    currency_sign = currency_info.get("sign", "$")

    if budget_info.get("minimum") and budget_info.get("maximum"):
        budget = f"{currency_sign}{budget_info['minimum']:.0f} - {currency_sign}{budget_info['maximum']:.0f}"
    elif budget_info.get("minimum"):
        budget = f"{currency_sign}{budget_info['minimum']:.0f}"
    else:
        budget = ""

    # Tipo de proyecto: fixed, hourly, etc.
    project_type = project.get("type", "")

    # Descripcion
    description = project.get("preview_description", "")
    if not description:
        description = project.get("description", "")

    # URL del proyecto
    seo_url = project.get("seo_url", "")
    if seo_url:
        url = f"https://www.freelancer.com/projects/{seo_url}"
    else:
        url = f"https://www.freelancer.com/projects/{project.get('id', '')}"

    # Timestamp
    submitdate = project.get("submitdate", 0)
    posted_date = ""
    if submitdate:
        from datetime import datetime, timezone
        posted_date = datetime.fromtimestamp(submitdate, tz=timezone.utc).isoformat()

    # Bid stats
    bid_stats = project.get("bid_stats", {})
    bid_count = bid_stats.get("bid_count", 0)

    # Jobs (categorias de Freelancer)
    job_ids = project.get("jobs", [])
    tags = [f"job_id_{j}" for j in job_ids] if job_ids else []

    return {
        "source": "freelancer",
        "external_id": str(project.get("id", "")),
        "title": project.get("title", "").strip(),
        "company": "Freelancer Client",  # Freelancer no expone nombre del cliente en API publica
        "description": description[:5000],
        "url": url,
        "location": "Remote (Freelancer.com)",
        "remote": True,
        "tags": tags,
        "salary": f"{budget} ({project_type})" if budget and project_type else budget or project_type,
        "posted_date": posted_date,
        "search_query": search_query,
        "bid_count": bid_count,  # extra: cuantos ya pujaron
    }


def fetch(config: dict) -> list[dict]:
    """Punto de entrada. Lee todos los queries configurados.

    config = {
        "enabled": true,
        "searches": {
            "docker_devops": "docker devops kubernetes",
            "python_automation": "python automation scraping",
            ...
        },
        "limit": 20,  # jobs por query
    }
    """
    if not config.get("enabled", False):
        return []

    searches = config.get("searches", {})
    if not searches:
        print("[freelancer] No hay busquedas configuradas")
        return []

    limit = config.get("limit", 20)
    all_jobs = []

    for search_name, query in searches.items():
        print(f"  [freelancer] Buscando: {search_name} -> '{query}'")

        data = _fetch_jobs(query, limit=limit)

        if data and data.get("result", {}).get("projects"):
            projects = data["result"]["projects"]
            for project in projects:
                job = _parse_project(project, search_name)
                all_jobs.append(job)
            print(f"    -> {len(projects)} jobs encontrados")
        else:
            print(f"    -> 0 jobs")

        # Rate limit entre queries
        if len(searches) > 1:
            wait = random.uniform(RATE_LIMIT_MIN, RATE_LIMIT_MAX)
            time.sleep(wait)

    print(f"  [freelancer] Total: {len(all_jobs)} jobs de {len(searches)} busquedas")
    return all_jobs
