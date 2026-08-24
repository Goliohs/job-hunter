"""
LinkedIn Easy Apply scraper with cookie support.
"""
import httpx
import asyncio
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import json
from pathlib import Path

# Load credentials
try:
    from auto_apply.credentials import LINKEDIN_COOKIES
except ImportError:
    LINKEDIN_COOKIES = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def build_cookie_header(cookies: dict) -> str:
    """Build Cookie header from cookie dict."""
    return "; ".join([f"{k}={v}" for k, v in cookies.items()])


def build_search_params(keywords: str, location: str = "Remote", page: int = 0, easy_apply_only: bool = True) -> dict:
    """Build LinkedIn search parameters."""
    params = {
        "keywords": keywords,
        "location": location,
        "position": 1,
        "pageNum": page,
        "start": page * 25,
    }
    if easy_apply_only:
        params["f_AL"] = "true"
    return params


async def fetch_linkedin_jobs(
    keywords: List[str],
    location: str = "Remote",
    max_pages: int = 3,
    cookies: dict = None,
    easy_apply_only: bool = True,
) -> List[Dict]:
    """Fetch jobs from LinkedIn job search API."""
    from typing import List, Dict
    
    if cookies is None:
        cookies = {}
    
    # Load cookies from credentials file if available
    try:
        from auto_apply.credentials import LINKEDIN_COOKIES
        if not cookies:
            cookies = LINKEDIN_COOKIES
    except ImportError:
        pass
    
    all_jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookies:
        headers["Cookie"] = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    
    LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    
    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:
        for keyword in keywords:
            for page in range(3):
                params = {
                    "keywords": keyword,
                    "location": "Remote",
                    "position": 1,
                    "pageNum": page,
                    "start": page * 25,
                }
                if True:  # easy_apply_only
                    params["f_AL"] = "true"
                
                try:
                    resp = await client.get(
                        "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
                        params=params,
                        timeout=30,
                        follow_redirects=True
                    )
                    resp.raise_for_status()
                except Exception as e:
                    print(f"[linkedin] Error fetching page: {e}")
                    break
                
                jobs = parse_linkedin_response(resp.text, keyword)
                if not jobs:
                    break
                
                all_jobs.extend(jobs)
                await asyncio.sleep(2)
    
    return all_jobs


def parse_linkedin_response(html: str, keyword: str) -> list:
    """Parse LinkedIn job search response HTML."""
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html, "html.parser")
    jobs = []
    
    # LinkedIn guest API returns li elements with job cards
    job_cards = soup.find_all("li", class_="job-result-card")
    if not job_cards:
        job_cards = soup.find_all("li", class_="base-search-card")
    if not job_cards:
        job_cards = soup.find_all("li", class_="base-search-card")
    
    for card in job_cards:
        try:
            # Title and link
            title_link = card.find("a", class_="base-card__full-link") or card.find("a", class_="job-result-card__link")
            if not title_link:
                continue
            
            title = title_link.get_text(strip=True)
            job_url = title_link.get("href", "")
            
            # Company
            company_elem = card.find("h4", class_="base-search-card__subtitle")
            company = company_elem.get_text(strip=True) if company_elem else ""
            
            # Location
            location_elem = card.find("span", class_="job-search-card__location")
            location = location_elem.get_text(strip=True) if location_elem else ""
            
            # Easy Apply badge
            easy_apply = card.find(string=lambda t: t and "Easy Apply" in t) is not None
            
            # External ID from URL
            external_id = ""
            if job_url:
                match = re.search(r"/jobs/view/(\d+)", job_url)
                if match:
                    external_id = match.group(1)
            
            # Check if remote
            is_remote = "remote" in location.lower() or "anywhere" in location.lower() or "worldwide" in location.lower()
            
            job = {
                "source": "linkedin",
                "external_id": external_id,
                "title": title,
                "company": company,
                "description": f"LinkedIn: {title} at {company} ({location})",
                "url": job_url,
                "location": location,
                "remote": is_remote,
                "tags": [],
                "salary": "",
                "posted_date": "",
                "easy_apply": True,  # We only fetch Easy Apply jobs
            }
            jobs.append(job)
        except Exception as e:
            print(f"[linkedin] Error parsing card: {e}")
            continue
    
    return jobs


def get_linkedin_cookies_from_browser(browser: str = "chrome") -> dict:
    """Extract LinkedIn cookies from browser."""
    try:
        import browser_cookie3
        if browser == "chrome":
            cookie_jar = browser_cookie3.chrome(domain_name="linkedin.com")
        elif browser == "firefox":
            cookie_jar = browser_cookie3.firefox(domain_name="linkedin.com")
        elif browser == "brave":
            cookie_jar = browser_cookie3.brave(domain_name="linkedin.com")
        elif browser == "edge":
            cookie_jar = browser_cookie3.edge(domain_name="linkedin.com")
        else:
            cookie_jar = browser_cookie3.chrome(domain_name="linkedin.com")
        
        cookies = {}
        for cookie in cookie_jar:
            cookies[cookie.name] = cookie.value
        return cookies
    except ImportError:
        print("browser_cookie3 not installed. Install with: pip install browser_cookie3")
        return {}
    except Exception as e:
        print(f"Error extracting cookies: {e}")
        return {}


# Load cookies from credentials file
def load_linkedin_cookies() -> dict:
    """Load LinkedIn cookies from credentials file."""
    try:
        from auto_apply.credentials import LINKEDIN_COOKIES
        return LINKEDIN_COOKIES
    except ImportError:
        return {}

# For backward compatibility
LINKEDIN_COOKIES = {}


if __name__ == "__main__":
    import asyncio
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    async def test():
        # Test with credentials
        from auto_apply.credentials import LINKEDIN_COOKIES
        jobs = await fetch_linkedin_jobs(
            keywords=["devops"],
            location="Remote",
            max_pages=1,
            cookies=LINKEDIN_COOKIES,
            easy_apply_only=True,
        )
        print(f"Found {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"  {job['title']} @ {job['company']} -> {job['url']}")
    
    asyncio.run(test())