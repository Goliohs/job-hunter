"""Wellfound (AngelList) job scraper."""
import httpx
import time
from typing import List, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


SEARCH_URLS = [
    "https://wellfound.com/jobs?locations[]=Remote&roles[]=Software%20Engineer&roles[]=DevOps%20Engineer&roles[]=Data%20Engineer&roles[]=Backend%20Engineer&roles[]=Fullstack%20Engineer&roles[]=Platform%20Engineer&roles[]=SRE",
    "https://wellfound.com/jobs?locations[]=Remote&roles[]=Engineering%20Manager&roles[]=CTO&roles[]=VP%20Engineering&roles[]=Staff%20Engineer&roles[]=Principal%20Engineer",
    "https://wellfound.com/jobs?locations[]=Remote&roles[]=AI%20Engineer&roles[]=ML%20Engineer&roles[]=Data%20Scientist",
]


def is_remote_job(text: str) -> bool:
    """Check if job text indicates remote work."""
    text_lower = text.lower()
    remote_keywords = ["remote", "anywhere", "worldwide", "global", "work from home", "wfh", "distributed", "telecommute"]
    exclude_keywords = ["hybrid", "onsite", "on-site", "office", "relocate", "relocation required"]
    
    has_remote = any(kw in text_lower for kw in remote_keywords)
    has_exclude = any(kw in text_lower for kw in exclude_keywords)
    
    return has_remote and not has_exclude


def fetch_page(url: str, timeout: int = 30) -> str | None:
    """Fetch a page with retries."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        print(f"[wellfound] HTTP {resp.status_code} for {url}")
    except Exception as e:
        print(f"[wellfound] Error fetching {url}: {e}")
    return None


def parse_job_card(card, base_url: str) -> Dict | None:
    """Parse a single job card from Wellfound listing."""
    try:
        # Job title and link
        title_link = card.select_one('a[href*="/jobs/"]')
        if not title_link:
            return None
        
        title = title_link.get_text(strip=True)
        job_url = title_link.get("href", "")
        if not job_url.startswith("http"):
            job_url = urljoin(base_url, job_url)
        
        # Company
        company_elem = card.select_one('a[href*="/company/"]')
        company = company_elem.get_text(strip=True) if company_elem else "Unknown"
        
        # Location
        location_elem = card.select_one('[data-test="job-location"]')
        location = location_elem.get_text(strip=True) if location_elem else ""
        
        # Full text for remote check
        full_text = card.get_text(" ", strip=True)
        
        if not is_remote_job(full_text):
            return None
        
        # Salary if available
        salary_elem = card.select_one('[data-test="job-salary"]')
        salary = salary_elem.get_text(strip=True) if salary_elem else ""
        
        # Tags/skills
        tags = []
        tag_elems = card.select('[data-test="job-tag"], .styles_tag__')
        for tag in tag_elems:
            t = tag.get_text(strip=True)
            if t:
                tags.append(t)
        
        # External ID from URL
        external_id = job_url.split("/")[-1].split("?")[0]
        
        return {
            "source": "wellfound",
            "external_id": external_id,
            "title": title,
            "company": company,
            "description": full_text[:5000],
            "url": job_url,
            "location": location or "Remote",
            "remote": True,
            "tags": tags,
            "salary": salary,
            "posted_date": "",
        }
    except Exception as e:
        print(f"[wellfound] Error parsing card: {e}")
        return None


def fetch_search_page(url: str, max_pages: int = 5) -> List[Dict]:
    """Fetch and parse a search results page with pagination."""
    all_jobs = []
    
    for page_num in range(1, max_pages + 1):
        page_url = f"{url}&page={page_num}" if page_num > 1 else url
        print(f"[wellfound] Fetching page {page_num}: {page_url}")
        
        html = fetch_page(page_url)
        if not html:
            break
        
        soup = BeautifulSoup(html, "html.parser")
        
        # Find job cards
        job_cards = soup.select('[data-test="job-card"], .styles_jobCard__')
        
        if not job_cards:
            # Try alternative selectors
            job_cards = soup.select('div[role="listitem"]')
        
        if not job_cards:
            print(f"[wellfound] No job cards found on page {page_num}")
            break
        
        page_jobs = 0
        for card in job_cards:
            job = parse_job_card(card, "https://wellfound.com")
            if job:
                all_jobs.append(job)
                page_jobs += 1
        
        print(f"[wellfound] Page {page_num}: {page_jobs} remote jobs")
        
        if page_jobs == 0:
            break
        
        time.sleep(2)  # Rate limit
    
    return all_jobs


def fetch(config: dict) -> List[Dict]:
    """Main entry point."""
    sources = config.get("sources", {}).get("wellfound", {})
    if not sources.get("enabled", False):
        return []
    
    all_jobs = []
    search_urls = sources.get("search_urls", SEARCH_URLS)
    max_pages = sources.get("max_pages", 3)
    
    for url in search_urls:
        try:
            jobs = fetch_search_page(url, max_pages)
            all_jobs.extend(jobs)
            time.sleep(3)
        except Exception as e:
            print(f"[wellfound] Error with {url}: {e}")
    
    print(f"[wellfound] Total remote jobs: {len(all_jobs)}")
    return all_jobs


if __name__ == "__main__":
    import yaml
    with open("/home/Helios/job-hunter/config.yaml") as f:
        config = yaml.safe_load(f)
    
    # Test with enabled
    config.setdefault("sources", {})["wellfound"] = {"enabled": True, "search_urls": SEARCH_URLS, "max_pages": 2}
    jobs = fetch(config)
    print(f"\nTotal: {len(jobs)}")
    for job in jobs[:5]:
        print(f"  - {job['title']} @ {job['company']} ({job['url']})")