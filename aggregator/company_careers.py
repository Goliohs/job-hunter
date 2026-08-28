"""Company career pages scraper for job-hunter."""
import httpx
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from typing import List, Dict
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
    "supabase": "https://supabase.com/careers",
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
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []
        
        # Try multiple selectors for different career page formats
        job_elements = (
            soup.find_all("a", href=re.compile(r"/jobs/")) or
            soup.find_all("a", href=re.compile(r"/careers/")) or
            soup.find_all("a", href=re.compile(r"/jobs/")) or
            soup.select("a[href*='/jobs/']") or
            soup.select("a[href*='/careers/']")
        )
        
        for link in job_elements[:limit]:
            try:
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue
                
                url = link.get("href", "")
                if not url.startswith("http"):
                    url = urljoin(url, url)
                
                # Try to find company/location nearby
                parent = link.find_parent("div") or link.find_parent("li") or link.find_parent("article")
                company = ""
                location = ""
                description = ""
                
                if parent:
                    text = parent.get_text(strip=True)
                    if len(text) > len(title):
                        # Extract additional info
                        remaining = text.replace(link.get_text(strip=True), "").strip()
                        if remaining:
                            description = remaining[:500]
                
                jobs.append({
                    "source": "company_career",
                    "external_id": "",
                    "title": link.get_text(strip=True),
                    "company": "",
                    "description": "",
                    "url": url,
                    "location": "",
                    "remote": True,  # Assume remote-friendly for tech companies
                    "tags": [],
                    "salary": "",
                    "posted_date": "",
                })
                
                if len(jobs) >= limit:
                    break
            except Exception as e:
                continue
        
        return jobs
    except Exception as e:
        print(f"[career_pages] Error fetching {url}: {e}")
        return []


def fetch_all_company_careers(config: dict, limit_per_company: int = 50) -> Dict[str, List[Dict]]:
    """Fetch jobs from all configured company career pages."""
    # Read from config
    config = load_config()
    companies = config.get("sources", {}).get("company_career_pages", {})
    
    if not companies.get("enabled"):
        return {}
    
    urls = companies.get("urls", COMPANY_CAREER_PAGES)
    limit = companies.get("limit_per_company", 50)
    
    all_results = {}
    for company, url in urls.items():
        jobs = fetch_company_careers(company, url, limit=limit_per_company)
        all_results[company] = jobs
        print(f"  [company:{company}] {len(jobs)} jobs")
        time.sleep(1)  # Be nice to servers
    
    return all_results


if __name__ == "__main__":
    import yaml
    
    with open(Path(__file__).resolve().parent.parent / "config.yaml") as f:
        config = yaml.safe_load(f)
    
    results = fetch_all_company_careers(config)
    for source, jobs in results.items():
        print(f"\n{source}: {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"  - {job['title']} ({job['url']})")