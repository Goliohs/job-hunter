"""Scraper para WeWorkRemotely.com (RSS de Programming Jobs)"""
import httpx
from bs4 import BeautifulSoup


def fetch(config: dict) -> list[dict]:
    url = config["url"]

    base_rss = "https://weworkremotely.com"

    try:
        resp = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[wwr] Error: {e}")
        return []

    soup = BeautifulSoup(resp.content, "xml")
    items = soup.find_all("item")
    print(f"[wwr] Fetched {len(items)} jobs from RSS")

    jobs = []
    for item in items:
        title_raw = item.find("title").text if item.find("title") else ""
        # WWR titulos suelen ser "Company: Job Title"
        if ":" in title_raw:
            company, title = title_raw.split(":", 1)
            company = company.strip()
            title = title.strip()
        else:
            company = ""
            title = title_raw.strip()

        link = item.find("link").text if item.find("link") else ""
        description = item.find("description").text if item.find("description") else ""
        pub_date = item.find("pubDate").text if item.find("pubDate") else ""

        # Extraer external_id del link (WWR usa /remote-jobs/<id>)
        external_id = link.rstrip("/").split("/")[-1] if link else title_raw

        jobs.append(
            {
                "source": "wwr",
                "external_id": external_id,
                "title": title,
                "company": company,
                "description": BeautifulSoup(description, "html.parser").get_text()[:5000],
                "url": link,
                "location": "Remote",
                "remote": True,
                "tags": [],
                "salary": "",
                "posted_date": pub_date,
            }
        )

    return jobs
