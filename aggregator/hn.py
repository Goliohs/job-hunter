"""Scraper para 'Ask HN: Who is Hiring?' thread mensual de Hacker News.

  El thread se publica el día 1 de cada mes en news.ycombinator.com.
  Este módulo busca automáticamente el último thread activo.
  """
import httpx
import time
from datetime import datetime
from bs4 import BeautifulSoup


def find_latest_whos_hiring() -> str | None:
    """Busca el ID del último 'Ask HN: Who is hiring?' thread."""
    try:
        resp = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query": "Ask HN: Who is hiring",
                "tags": "story",
                "numericFilters": "points>50",
            },
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json()["hits"]
        if hits:
            for h in hits:
                if "who is hiring" in h.get("title", "").lower():
                    return str(h["objectID"])
    except Exception as e:
        print(f"[hn] Error buscando thread: {e}")
    return None


def fetch(config: dict) -> list[dict]:
    base_url = config.get("base_url", "https://news.ycombinator.com")
    thread_id = find_latest_whos_hiring()
    if not thread_id:
        print("[hn] No se encontró thread 'Who is hiring?'")
        return []

    print(f"[hn] Thread encontrado: {thread_id}")

    try:
        # HN API: no usar Algolia, iterar regularmente por paginación
        resp = httpx.get(
            f"https://hacker-news.firebaseio.com/v0/item/{thread_id}.json",
            timeout=20,
        )
        resp.raise_for_status()
        story = resp.json()
        kids = story.get("kids", [])[:100]  # primer 100 comentarios
    except Exception as e:
        print(f"[hn] Error obteniendo thread: {e}")
        return []

    print(f"[hn] {len(kids)} comentarios en el thread")

    jobs = []
    for kid_id in kids:
        try:
            r = httpx.get(
                f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json",
                timeout=10,
            )
            r.raise_for_status()
            comment = r.json()
        except Exception:
            continue

        if not comment or "text" not in comment:
            continue

        text = comment.get("text", "")
        # HN comentarios de Who's Hiring suelen empezar con "Company | Location | ..."
        # Filtro muy ligero: si tiene "|" en primer段落 y texto > 100 chars
        if len(text) < 100:
            continue

        soup = BeautifulSoup(text, "html.parser")
        clean_text = soup.get_text()
        # Intentar extraer "empresa" y "ubicación" de la primera línea
        first_line = clean_text.split("\n")[0][:200]
        parts = [p.strip() for p in first_line.split("|")]
        company = parts[0] if parts else "Unknown"
        title = parts[1] if len(parts) > 1 else "Position"

        # Filtro por "remote" o "worldwide" o "anywhere" en el texto
        text_lower = clean_text.lower()
        if not any(
            kw in text_lower
            for kw in ("remote", "worldwide", "anywhere", "global")
        ):
            continue

        # Extract actual job links from comment (Greenhouse, Lever, Ashby, company careers)
        job_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if any(ats in href for ats in ["greenhouse.io", "lever.co", "ashbyhq.com", "careers.", "jobs.", "workable.com", "recruitee.com", "teamtailor.com", "smartrecruiters.com"]):
                job_links.append(href)
        
        # Also look for bare URLs in text
        import re
        urls_in_text = re.findall(r'https?://[^\s\)]+', clean_text)
        for u in urls_in_text:
            if any(ats in u for ats in ["greenhouse.io", "lever.co", "ashbyhq.com", "careers.", "jobs.", "workable.com", "recruitee.com", "teamtailor.com", "smartrecruiters.com"]):
                job_links.append(u)

        # Use the first ATS link found, or fall back to HN comment URL
        apply_url = job_links[0] if job_links else f"{base_url}/item?id={kid_id}"
        
        url = apply_url
        jobs.append(
            {
                "source": "hackernews",
                "external_id": str(kid_id),
                "title": title[:150],
                "company": company[:100],
                "description": clean_text[:5000],
                "url": url,
                "location": "Remote",
                "remote": True,
                "tags": [],
                "salary": "",
                "posted_date": datetime.fromtimestamp(
                    comment.get("time", 0)
                ).isoformat(),
            }
        )

        # Rate limit suave
        time.sleep(0.05)

    print(f"[hn] {len(jobs)} jobs remotos encontrados en HN")
    return jobs
