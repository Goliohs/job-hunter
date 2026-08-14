"""Scraper para Lever career pages."""
import httpx
from typing import List, Dict
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re


def fetch(config: dict) -> List[Dict]:
    """Scrapea páginas de Lever career."""
    all_jobs = []
    # config is the lever source config directly (with enabled, urls)
    if not config.get("enabled"):
        return []

    for url in config.get("urls", []):
        try:
            print(f"  [lever] Fetching {url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            resp = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Lever job pages have job postings in specific containers
            # Try multiple selectors for different Lever page layouts
            job_links = soup.select('a.posting-title, a[href*="/jobs/"]')
            
            jobs = []
            for link in job_links:
                href = link.get("href", "")
                if not href:
                    continue
                    
                title_elem = link.select_one('.posting-title, .posting-title-text, h5, h3')
                title = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)
                
                if not title or len(title) < 3:
                    continue
                    
                company = "Unknown"
                # Try to find company name
                parent = link.find_parent()
                for _ in range(3):
                    if parent:
                        company_elem = parent.find(class_=re.compile(r'company|organization|org'))
                        if company_elem:
                            company = company_elem.get_text(strip=True)
                            break
                        parent = parent.find_parent()
                    else:
                        break
                
                if not company or company == "Unknown":
                    company = "Unknown"
                
                # Build URL
                href = link.get("href", "")
                if href.startswith("http"):
                    url = href
                else:
                    url = "https://jobs.lever.co" + href
                
                # Extract company from URL if possible
                company = "Unknown"
                if "jobs.lever.co/" in url:
                    parts = url.split("jobs.lever.co/")
                    if len(parts) > 1:
                        company = parts[1].split("/")[0]
                
# Try to get location
                location = "Remote"
                parent = link.find_parent()
                for _ in range(3):
                    if parent:
                        loc_elem = parent.find(class_=re.compile(r'location|location'))
                        if loc_elem:
                            loc_text = loc_elem.get_text(strip=True)
                            if loc_text:
                                location = loc_text
                                break
                        parent = parent.find_parent()
                    else:
                        break
                
                job = {
                    "source": "lever",
                    "external_id": link.get("href", "").split("/")[-1] if link.get("href") else "",
                    "title": title,
                    "company": company,
                    "description": "",
                    "url": link.get("href", "") if link.get("href", "").startswith("http") else f"https://jobs.lever.co{link.get('href', '')}",
                    "location": "Remote",
                    "remote": True,
                    "tags": [],
                    "salary": "",
                    "posted_date": "",
                }
                jobs.append(job)
            
            if jobs:
                print(f"  [lever] {len(jobs)} jobs found")
                yield from jobs
                
        except Exception as e:
            print(f"[lever] Error fetching {url}: {e}")
    
    return []