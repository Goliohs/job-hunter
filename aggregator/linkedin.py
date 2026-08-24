"""LinkedIn Jobs RSS scraper for job-hunter."""
import httpx
import feedparser
from typing import List, Dict, Optional
from datetime import datetime
import re
from bs4 import BeautifulSoup


LINKEDIN_SEARCH_URLS = {
    "devops_remote": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=devops%20OR%20site%20reliability%20OR%20platform%20engineer&location=Remote&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0",
    "fullstack_remote": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=full%20stack%20OR%20backend%20OR%20python%20OR%20golang&location=Remote&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0",
    "ai_ml_remote": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=ai%20OR%20machine%20learning%20OR%20llm%20OR%20mlops&location=Remote&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0",
    "frontend_remote": "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=react%20OR%20frontend%20OR%20typescript&location=Remote&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0",
}


def fetch_linkedin_jobs(search_name: str, url: str, limit: int = 50) -> List[Dict]:
    """Fetch jobs from LinkedIn RSS/HTML feed."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        
        # Parse HTML for job cards
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []
        
        # LinkedIn job cards have specific structure
        for card in soup.find_all("li", class_="job-result-card") or soup.find_all("div", class_="job-card-container"):
            try:
                title_elem = card.find("h3", class_="job-result-card__title") or card.find("h3", class_="base-search-card__title")
                company_elem = card.find("h4", class_="job-result-card__subtitle") or card.find("h4", class_="base-search-card__subtitle")
                location_elem = card.find("span", class_="job-result-card__location") or card.find("span", class_="job-search-card__location")
                link_elem = card.find("a", class_="job-result-card__link") or card.find("a", class_="base-card__full-link")
                
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                company = company_elem.get_text(strip=True) if company_elem else ""
                location = location_elem.get_text(strip=True) if location_elem else ""
                url = link_elem.get("href", "") if link_elem else ""
                
                # Check for remote
                is_remote = "remote" in location.lower() or "anywhere" in location.lower() or "worldwide" in location.lower()
                
                # Generate external ID from URL
                external_id = ""
                if url:
                    match = re.search(r"/jobs/view/(\d+)", url) or re.search(r"/jobs/(\d+)", url)
                    if match:
                        external_id = match.group(1)
                
                job = {
                    "source": "linkedin",
                    "external_id": external_id,
                    "title": title,
                    "company": company,
                    "description": f"LinkedIn: {title} at {company} ({location})",
                    "url": url,
                    "location": location,
                    "remote": is_remote,
                    "tags": [],
                    "salary": "",
                    "posted_date": datetime.now().isoformat(),
                }
                jobs.append(job)
                
                if len(jobs) >= limit:
                    break
            except Exception:
                continue
        
        return jobs
    except Exception as e:
        print(f"[linkedin] Error fetching {search_name}: {e}")
        return []


def fetch_all_linkedin_jobs(config: dict, limit_per_search: int = 50) -> Dict[str, List[Dict]]:
    """Fetch jobs from all LinkedIn searches."""
    sources = config.get("sources", {}).get("linkedin", {})
    if not sources.get("enabled"):
        return {}
    
    searches = sources.get("searches", LINKEDIN_SEARCH_URLS)
    all_results = {}
    
    for search_name, url in searches.items():
        if isinstance(url, dict):
            url = url.get("url", "")
        if not url:
            continue
        
        jobs = fetch_linkedin_jobs(search_name, url, limit=limit_per_search)
        all_results[search_name] = jobs
        print(f"  [linkedin:{search_name}] {len(jobs)} jobs")
    
    return all_results


if __name__ == "__main__":
    import yaml
    from bs4 import BeautifulSoup
    
    with open("/home/Helios/job-hunter/config.yaml") as f:
        config = yaml.safe_load(f)
    
    results = fetch_all_linkedin_jobs(config)
    for source, jobs in results.items():
        print(f"\n{source}: {len(jobs)} jobs")
        for job in jobs[:3]:
            print(f"  - {job['title']} @ {job['company']} ({job['location']})")
            print(f"    {job['url']}")