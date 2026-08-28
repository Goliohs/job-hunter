"""Aggregator para Upwork via RSS feeds oficiales.

Upwork provee feeds RSS publicos para cada busqueda:
  https://www.upwork.com/ab/feed/jobs/rss?params=<base64-json>

Esto NO es scraping: es el feed oficial que Upwork expone para lectores RSS.
No requiere login, no viola ToS, no usa la API privada.

Estrategia anti-ban:
  - Solo lee feeds RSS publicos (sin login, sin browser automation)
  - Rate limit generoso entre requests
  - User-Agent de lector RSS estandar
  - NO auto-aplica. Solo alerta al humano para que aplique manualmente.
"""
import httpx
import feedparser
import base64
import json
import time
import random
from typing import Optional

# User-Agent de lector RSS (no de browser, para ser claro que es feed reader)
RSS_USER_AGENT = "Mozilla/5.0 (compatible; RSS Reader/1.0; +https://github.com/youruser/job-hunter)"

# Rate limit entre feeds (segundos)
RATE_LIMIT_MIN = 5.0
RATE_LIMIT_MAX = 10.0


def _build_search_url(query: str, sort: str = "recency", paging: int = 0) -> str:
    """Construye la URL del RSS feed de Upwork para una busqueda.

    Upwork usa params en base64 JSON para el RSS feed.
    Formato: https://www.upwork.com/ab/feed/jobs/rss?params=<base64>
    """
    params = {
        "q": query,
        "sort": sort,
        "paging": paging,
    }
    params_json = json.dumps(params)
    params_b64 = base64.b64encode(params_json.encode()).decode()
    return f"https://www.upwork.com/ab/feed/jobs/rss?params={params_b64}"


def _build_simple_url(query: str, sort: str = "recency") -> str:
    """URL alternativa usando query params directos (algunos feeds lo soportan)."""
    # Upwork soporta query params simples en el RSS:
    # ?q=<query>&sort=recency&job_type=hourly&duration=...
    return (
        f"https://www.upwork.com/ab/feed/jobs/rss"
        f"?q={query.replace(' ', '+')}"
        f"&sort={sort}"
    )


def _fetch_feed(url: str, timeout: int = 30) -> Optional[dict]:
    """Descarga y parsea un feed RSS. Devuelve el dict parseado o None."""
    headers = {
        "User-Agent": RSS_USER_AGENT,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers)
        if resp.status_code != 200:
            print(f"  [upwork] HTTP {resp.status_code} for feed")
            return None
        # feedparser puede parsear desde string
        parsed = feedparser.parse(resp.content)
        if not parsed.entries:
            print(f"  [upwork] Feed sin entradas (posible bloqueo o cambio de formato)")
            return None
        return parsed
    except Exception as e:
        print(f"  [upwork] Error fetching feed: {e}")
        return None


def _parse_entry(entry, source_query: str) -> dict:
    """Normaliza una entrada del feed RSS de Upwork al formato del job-hunter."""
    # Upwork RSS entries tienen:
    #   title: "Job title - Budget - Posted X ago"
    #   link: URL al job
    #   summary: descripcion HTML del job
    #   author: nombre del cliente
    #   published: fecha

    raw_title = entry.get("title", "").strip()

    # Upwork a veces anexa budget info al titulo: "Docker setup - $200 - Posted 2h ago"
    # Extraer budget si esta presente
    budget = ""
    import re
    budget_match = re.search(r"\$[\d,]+(?:\.\d+)?(?:\s*/hr)?(?:\s*-\s*\$[\d,]+)?", raw_title)
    if budget_match:
        budget = budget_match.group(0)

    # Limpiar HTML del summary
    summary = entry.get("summary", "")
    if summary:
        # feedparser ya hace algo de cleanup, pero por si acaso
        import re as re2
        summary = re2.sub(r"<[^>]+>", " ", summary)  # quitar tags HTML
        summary = re2.sub(r"\s+", " ", summary).strip()

    # Extraer ID del job desde el link
    job_url = entry.get("link", "")
    external_id = ""
    # Upwork job URLs: https://www.upwork.com/jobs/~<id> o /~021xxxx
    id_match = re.search(r"~[a-f0-9]+", job_url)
    if id_match:
        external_id = id_match.group(0)
    else:
        # fallback: hash del titulo+url
        external_id = f"upwork_{hash(raw_title + job_url) & 0xFFFFFFFFFFFFFFFF:x}"

    return {
        "source": "upwork",
        "external_id": external_id,
        "title": raw_title,
        "company": entry.get("author", "Upwork Client"),  # cliente, no empresa
        "description": summary[:5000],  # truncate como remotive
        "url": job_url,
        "location": "Remote (Upwork)",
        "remote": True,
        "tags": [],  # Upwork RSS no expone tags directamente
        "salary": budget,
        "posted_date": entry.get("published", ""),
        "search_query": source_query,  #追踪 qué query lo encontro
    }


def fetch(config: dict) -> list[dict]:
    """Punto de entrada. Lee todos los feeds RSS configurados.

    config = {
        "enabled": true,
        "searches": {
            "docker_devops": "docker devops kubernetes",
            "python_automation": "python automation scraping",
            ...
        },
        "sort": "recency",  # o "relevance"
    }
    """
    if not config.get("enabled", False):
        return []

    searches = config.get("searches", {})
    if not searches:
        print("[upwork] No hay busquedas configuradas")
        return []

    sort = config.get("sort", "recency")
    all_jobs = []

    for search_name, query in searches.items():
        print(f"  [upwork] Buscando: {search_name} -> '{query}'")

        # Probar URL simple primero, fallback a base64
        url = _build_simple_url(query, sort)
        parsed = _fetch_feed(url)

        if not parsed or not parsed.entries:
            print(f"  [upwork] Feed simple fallo, probando base64...")
            url = _build_search_url(query, sort)
            parsed = _fetch_feed(url)

        if parsed and parsed.entries:
            for entry in parsed.entries:
                job = _parse_entry(entry, search_name)
                all_jobs.append(job)
            print(f"    -> {len(parsed.entries)} jobs encontrados")
        else:
            print(f"    -> 0 jobs (feed vacio o bloqueado)")

        # Rate limit entre feeds para no llamar atencion
        if len(searches) > 1:
            wait = random.uniform(RATE_LIMIT_MIN, RATE_LIMIT_MAX)
            print(f"    -> esperando {wait:.1f}s antes de siguiente feed...")
            time.sleep(wait)

    print(f"  [upwork] Total: {len(all_jobs)} jobs de {len(searches)} busquedas")
    return all_jobs
