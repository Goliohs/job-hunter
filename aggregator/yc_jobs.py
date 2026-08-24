"""Y Combinator Job Board scraper."""
import httpx
import time
from typing import List, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


YC_JOBS_URL = "https://www.ycombinator.com/jobs"


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
        print(f"[yc_jobs] HTTP {resp.status_code} for {url}")
    except Exception as e:
        print(f"[yc_jobs] Error fetching {url}: {e}")
    return None


def parse_job_card(card, base_url: str) -> Dict | None:
    """Parse a single job card from YC jobs listing."""
    try:
        # Job title and link
        title_link = card.select_one('a[href*="/jobs/"]')
        if not title_link:
            return None
        
        title = title_link.get_text(strip=True)
        job_url = title_link.get("href", "")
        if not job_url.startswith("http"):
            job_url = urljoin(base_url, job_url)
        
        # Company - usually in a sibling element
        company_elem = card.select_one('[class*="company"], [class*="Company"]')
        company = company_elem.get_text(strip=True) if company_elem else ""
        
        # If no company element, try to find it near the title
        if not company:
            # Look for text that looks like a company name
            all_text = card.get_text(" ", strip=True)
            # Try to extract from the structure
            pass
        
        # Location
        location_elem = card.select_one('[class*="location"], [class*="Location"]')
        location = location_elem.get_text(strip=True) if location_elem else ""
        
        # Full text for remote check
        full_text = card.get_text(" ", strip=True)
        
        if not is_remote_job(full_text):
            return None
        
        # Tags/skills
        tags = []
        tag_elems = card.select('[class*="tag"], [class*="Tag"], [class*="skill"], [class*="Skill"]')
        for tag in tag_elems:
            t = tag.get_text(strip=True)
            if t and len(t) < 30:
                tags.append(t)
        
        # External ID from URL
        external_id = job_url.split("/")[-1].split("?")[0]
        
        return {
            "source": "yc_jobs",
            "external_id": external_id,
            "title": title,
            "company": company or "YC Company",
            "description": full_text[:5000],
            "url": job_url,
            "location": location or "Remote",
            "remote": True,
            "tags": tags,
            "salary": "",
            "posted_date": "",
        }
    except Exception as e:
        print(f"[yc_jobs] Error parsing card: {e}")
        return None


def fetch_yc_jobs(max_pages: int = 10) -> List[Dict]:
    """Fetch and parse YC jobs with pagination."""
    all_jobs = []
    
    for page_num in range(1, max_pages + 1):
        page_url = f"{YC_JOBS_URL}?page={page_num}" if page_num > 1 else YC_JOBS_URL
        print(f"[yc_jobs] Fetching page {page_num}: {page_url}")
        
        html = fetch_page(page_url)
        if not html:
            break
        
        soup = BeautifulSoup(html, "html.parser")
        
        # YC uses a specific structure - look for job cards
        # Try multiple selectors
        job_cards = (
            soup.select('[data-test="job-card"]') or
            soup.select('.job-card') or
            soup.select('[class*="JobCard"]') or
            soup.select('article[class*="job"]') or
            soup.select('div[class*="job"]') or
            soup.select('li[class*="job"]')
        )
        
        if not job_cards:
            # Try to find via links
            links = soup.select('a[href*="/jobs/"]')
            # Group by parent
            for link in links:
                parent = link.find_parent(['div', 'article', 'li', 'section'])
                if parent:
                    job_cards.append(parent)
            # Deduplicate
            seen = set()
            unique_cards = []
            for card in job_cards:
                card_id = id(card)
                if card_id not in seen:
                    seen.add(card_id)
                    unique_cards.append(card)
            job_cards = unique_cards
        
        if not job_cards:
            print(f"[yc_jobs] No job cards found on page {page_num}")
            # Print some debug info
            links = soup.select('a[href*="/jobs/"]')
            print(f"[yc_jobs] Found {len(links)} job links")
            break
        
        page_jobs = 0
        for card in job_cards:
            job = parse_job_card(card, "https://www.ycombinator.com")
            if job:
                all_jobs.append(job)
                page_jobs += 1
        
        print(f"[yc_jobs] Page {page_num}: {page_jobs} remote jobs")
        
        if page_jobs == 0:
            break
        
        time.sleep(2)
    
    return all_jobs


def fetch(config: dict) -> List[Dict]:
    """Main entry point."""
    sources = config.get("sources", {}).get("yc_jobs", {})
    if not sources.get("enabled", False):
        return []
    
    max_pages = sources.get("max_pages", 10)
    
    try:
        jobs = fetch_yc_jobs(max_pages)
        print(f"[yc_jobs] Total remote jobs: {len(jobs)}")
        return jobs
    except Exception as e:
        print(f"[yc_jobs] Error: {e}")
        return []


if __name__ == "__main__":
    import yaml
    with open("/home/Helios/job-hunter/config.yaml") as f:
        config = yaml.safe_load(f)
    
    config.setdefault("sources", {})["yc_jobs"] = {"enabled": True, "max_pages": 3}
    jobs = fetch(config)
    print(f"\nTotal: {len(jobs)}")
    for job in jobs[:5]:
        print(f"  - {job['title']} @ {job['company']} ({job['url']})")