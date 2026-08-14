"""Scraper para RemoteOK.com (API JSON pública)"""
import httpx


def fetch(config: dict) -> list[dict]:
    url = config["url"]

    try:
        # RemoteOK necesita un User-Agent, sino da 403
        resp = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[remoteok] Error: {e}")
        return []

    # RemoteOK devuelve [{}, {job1}, {job2}, ...] — el primer item es metadata
    jobs_raw = [j for j in data if j.get("id")]
    print(f"[remoteok] Fetched {len(jobs_raw)} jobs from API")

    jobs = []
    for j in jobs_raw:
        # Solo remoto (RemoteOK ya filtra, pero por seguridad)
        location = j.get("location", "")
        if location and "remote" not in location.lower() and location != "Anywhere":
            if "worldwide" not in location.lower():
                continue

        jobs.append(
            {
                "source": "remoteok",
                "external_id": str(j.get("id", "")),
                "title": j.get("position", "").strip(),
                "company": j.get("company", "").strip(),
                "description": j.get("description", "")[:5000],
                "url": j.get("url", ""),
                "location": location,
                "remote": True,
                "tags": j.get("tags", [])[:15],
                "salary": j.get("salary", ""),
                "posted_date": j.get("date", ""),
            }
        )

    return jobs
