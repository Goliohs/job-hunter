"""Company career pages scraper for job-hunter."""
import httpx
from typing import List, Dict
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin
import time


from pathlib import Path
COMPANY_CAREER_PAGES = {
    # Tech companies with good career pages
    "canonical": "https://careers.canonical.com/jobs",
    "elastic": "https://www.elastic.co/careers",
    "hashicorp": "https://www.hashicorp.com/careers",
    "grafana": "https://grafana.com/careers",
    "prometheus": "https://prometheus.io/careers/",
    "cockroachdb": "https://www.cockroachlabs.com/careers/",
    "singlestore": "https://www.singlestore.com/careers/",
    "timescale": "https://www.timescale.com/careers",
    "materialize": "https://materialize.com/careers/",
    "clickhouse": "https://clickhouse.com/careers",
    "tinybird": "https://www.tinybird.co/careers",
    "pagerduty": "https://www.pagerduty.com/careers/",
    "gitlab": "https://about.gitlab.com/jobs/",
    "supabase": "https://supabase.com/careers",
    "vercel": "https://vercel.com/careers",
    "planetscale": "https://planetscale.com/careers",
    "railway": "https://railway.app/careers",
    "render": "https://render.com/careers",
    "fly.io": "https://fly.io/careers",
    "cloudflare": "https://www.cloudflare.com/careers/",
    "datadog": "https://www.datadoghq.com/careers/",
    "newrelic": "https://newrelic.com/careers",
    "sentry": "https://sentry.io/careers/",
    "posthog": "https://posthog.com/careers",
    "linear": "https://linear.app/careers",
    "notion": "https://www.notion.so/careers",
    "figma": "https://www.figma.com/careers",
    "linear": "https://linear.app/careers",
    "airbyte": "https://airbyte.com/careers",
    "fivetran": "https://fivetran.com/careers",
    "dbt": "https://www.getdbt.com/careers/",
    "prefect": "https://www.prefect.io/careers",
    "dagster": "https://dagster.io/careers",
    "airflow": "https://airflow.apache.org/community/careers/",
    "dbt": "https://www.getdbt.com/careers/",
    "prefect": "https://www.prefect.io/careers",
    "dagster": "https://dagster.io/careers",
    "airflow": "https://airflow.apache.org/community/careers/",
}


def fetch_company_careers(company: str, url: str, limit: int = 50) -> List[Dict]:
    """Fetch jobs from a company's career page."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []
        
        # Try multiple selectors for different career page formats
        job_elements = (
            soup.select('a[href*="/jobs/"]') or
            soup.select('a[href*="/jobs/"]') or
            soup.select('a[href*="/careers/"]') or
            soup.select('a[href*="/career/"]') or
            soup.select('a[href*="/job/"]') or
            soup.select('[data-testid*="job"]') or
            soup.select('[data-testid*="job-card"]') or
            soup.select('.job-card, .job-listing, .position, .opening')
        )
        
        for link in job_elements:
            href = link.get("href", "")
            if not href or not href.startswith(("http", "/")):
                continue
            
            # Try to extract title
            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue
            
            # Make absolute URL
            full_url = urljoin(link.get("href", ""), link.get("href", "")) if link.get("href", "").startswith("/") else link.get("href", "")
            if not full_url.startswith("http"):
                full_url = urljoin(url, link.get("href", ""))
            
            # Try to find company name from page
            title_text = title_elem.get_text(strip=True) if (title_elem := link.find(["h3", "h4", "h5", "h2", "span", "div"])) else ""
            if not title_text:
                title_text = link.get_text(strip=True)
            
            # Check if remote
            text = link.get_text(" ", strip=True).lower()
            is_remote = any(kw in link.get_text(" ", strip=True).lower() for kw in ["remote", "remote", "anywhere", "worldwide", "global"])
            
            # Try to find location
            location = ""
            for sibling in link.find_all_next(["span", "div", "p", "li"]):
                text = sibling.get_text(strip=True)
                if any(kw in text.lower() for kw in ["remote", "remote", "anywhere", "worldwide", "hybrid", "onsite", "onsite"]):
                    location = text
                    break
            
            # Generate external ID
            external_id = re.sub(r'[^\w\-]', '_', title)[:50]
            
            job = {
                "source": "company_career",
                "external_id": f"{company}-{re.sub(r'[^\w\-]', '_', title)[:40]}",
                "title": title,
                "company": company,
                "description": f"Company career page: {title}",
                "url": full_url,
                "location": location or "Remote",
                "remote": is_remote or "remote" in link.get_text().lower(),
                "tags": [],
                "salary": "",
                "posted_date": datetime.now().isoformat(),
            }
            jobs.append(job)
            
            if len(jobs) >= limit:
                break
        
        return jobs
    except Exception as e:
        print(f"[company_career] Error fetching {company}: {e}")
        return []


def fetch(config: dict) -> List[Dict]:
    """Fetch jobs from all configured company career pages."""
    sources = config.get("sources", {}).get("company_career_pages", {})
    if not sources.get("enabled"):
        return []
    
    all_jobs = []
    
    for company, url in COMPANY_CAREER_PAGES.items():
        try:
            print(f"  [company_career:{company}] Fetching...")
            jobs = fetch_company_careers(company, url, limit=50)
            all_jobs.extend(jobs)
            print(f"  [{company}] {len(jobs)} jobs")
            time.sleep(1)  # Be respectful
        except Exception as e:
            print(f"  [{company}] Error: {e}")
    
    return all_jobs


if __name__ == "__main__":
    import yaml
    from datetime import datetime
    
    with open(Path(__file__).resolve().parent.parent / "config.yaml") as f:
        config = yaml.safe_load(f)
    
    jobs = fetch({"sources": {"company_career_pages": {"enabled": True}}})
    print(f"\nTotal jobs: {len(jobs)}")
    for job in jobs[:5]:
        print(f"  - {job['title']} @ {job['company']} ({job['url']})")