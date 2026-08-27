"""Scraper para company career pages que usan Lever/Greenhouse/Ashby."""
import httpx
import time
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def is_remote_job(text: str) -> bool:
    """Check if job text indicates remote work."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in [
        "remote", "anywhere", "worldwide", "global", "work from home", 
        "wfh", "distributed", "telecommute"
    ]) and "hybrid" not in text_lower


def fetch_page(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch a page with retries."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        print(f"[ats_career] HTTP {resp.status_code} for {url}")
    except Exception as e:
        print(f"[ats_career] Error fetching {url}: {e}")
    return None


def parse_greenhouse(html: str, base_url: str, company: str = "") -> List[Dict]:
    """Parse Greenhouse job board page - remote jobs only."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    table = soup.select_one(".job-posts--table")
    if not table:
        return jobs

    rows = table.find_all("tr")
    for row in rows[1:]:  # Skip header
        link = row.select_one("a")
        if not link:
            continue
        
        title = link.get_text(strip=True)
        job_url = link.get("href", "")
        if not job_url.startswith("http"):
            job_url = f"https://job-boards.greenhouse.io{job_url}"
        
        full_text = row.get_text(strip=True)
        
        if is_remote_job(full_text):
            # Extract company from base_url path
            if not company:
                parsed = urlparse(base_url)
                path_parts = parsed.path.strip("/").split("/")
                company = path_parts[0] if path_parts else ""
            
            jobs.append({
                "source": "greenhouse_career",
                "external_id": job_url.split("/")[-1],
                "title": title,
                "company": company,
                "description": "",
                "url": job_url,
                "location": "Remote",
                "remote": True,
                "tags": [],
                "salary": "",
                "posted_date": "",
            })
    
    return jobs


def is_remote_job(text: str) -> bool:
    """Check if job text indicates remote work."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in [
        "remote", "anywhere", "worldwide", "global", "work from home", 
        "wfh", "distributed", "telecommute"
    ]) and "hybrid" not in text_lower


def parse_lever(html: str, base_url: str) -> List[Dict]:
    """Parse Lever job board page."""
    soup = BeautifulSoup(html, "html.parser")
    jobs = []

    for link in soup.select('a[href*="/jobs/"]'):
        href = link.get("href", "")
        if not href:
            continue
        
        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            continue
        
        full_url = urljoin(base_url, href)
        full_text = link.get_text(" ", strip=True)
        
        parent = link.find_parent("div", class_=re.compile(r"posting|job"))
        if parent:
            full_text += " " + parent.get_text(" ", strip=True)
        
        if is_remote_job(full_text):
            company = urlparse(base_url).netloc.replace("jobs.", "").replace(".lever.co", "").title()
            jobs.append({
                "source": "lever_career",
                "external_id": href.split("/")[-1],
                "title": title,
                "company": company,
                "description": "",
                "url": full_url,
                "location": "Remote",
                "remote": True,
                "tags": [],
                "salary": "",
                "posted_date": "",
            })
    
    return jobs


def fetch_page(url: str, timeout: int = 30) -> Optional[str]:
    """Fetch a page with retries."""
    try:
        resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
        print(f"[ats_career] HTTP {resp.status_code} for {url}")
    except Exception as e:
        print(f"[ats_career] Error fetching {url}: {e}")
    return None


def fetch_greenhouse_career(url: str) -> List[Dict]:
    """Fetch Greenhouse career page (uses job-boards.greenhouse.io)."""
    parsed = urlparse(url)
    if "job-boards.greenhouse.io" in parsed.netloc:
        # Already in job-boards format: https://job-boards.greenhouse.io/company
        path_parts = parsed.path.strip("/").split("/")
        company = path_parts[0] if path_parts else ""
    elif "boards.greenhouse.io" in parsed.netloc:
        # Convert boards.greenhouse.io to job-boards format
        # parsed.netloc = "boards.greenhouse.io" -> extract company from path
        path_parts = parsed.path.strip("/").split("/")
        company = path_parts[0] if path_parts else ""
    else:
        # Assume URL is just a company name or path
        path_parts = parsed.path.strip("/").split("/")
        company = path_parts[0] if path_parts else ""
    
    if not company:
        return []
    
    job_boards_url = f"https://job-boards.greenhouse.io/{company}"
    
    print(f"[greenhouse_career] Fetching {job_boards_url}")
    html = fetch_page(job_boards_url)
    if not html:
        return []
    return parse_greenhouse(html, job_boards_url)


def fetch_lever_career(url: str) -> List[Dict]:
    """Fetch Lever career page."""
    print(f"[lever_career] Fetching {url}")
    html = fetch_page(url)
    if not html:
        return []
    return parse_lever(html, url)


def fetch_ashby_career(url: str) -> List[Dict]:
    """Fetch Ashby career page via su API pública posting-api."""
    parsed = urlparse(url)
    company = parsed.path.strip("/").split("/")[0]
    if not company:
        return []

    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
    print(f"[ashby_career] Fetching {api_url}")
    try:
        resp = httpx.get(api_url, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            print(f"[ashby_career] HTTP {resp.status_code} for {api_url}")
            return []
        data = resp.json()
    except Exception as e:
        print(f"[ashby_career] Error fetching {api_url}: {e}")
        return []

    jobs = []
    for j in data.get("jobs", []):
        if not j.get("isListed", True):
            continue

        location = j.get("location", "") or ""
        title = j.get("title", "")
        workplace = (j.get("workplaceType", "") or "").lower()
        # Evaluar remote en: isRemote + workplaceType + location + título
        remote_text = f"{location} {title}"
        is_remote = bool(j.get("isRemote"))
        if not is_remote:
            if workplace in ("remote", "fully remote", "remote-first", "hybrid"):
                is_remote = workplace != "hybrid"
            elif is_remote_job(remote_text):
                is_remote = True

        desc = j.get("descriptionPlain", "") or ""
        job_url = j.get("jobUrl") or j.get("applyUrl") or ""
        if not title or not job_url:
            continue

        jobs.append({
            "source": "ashby_career",
            "external_id": j.get("id") or job_url.split("/")[-1],
            "title": title,
            "company": company,
            "description": desc[:4000],
            "url": job_url,
            "location": location or "Remote",
            "remote": is_remote,
            "tags": [],
            "salary": "",
            "posted_date": (j.get("publishedAt") or "")[:10],
        })

    return jobs


def fetch(config: dict) -> List[Dict]:
    """Main entry point - fetches from all configured ATS career pages."""
    all_jobs = []
    
    # config is the ats_career_pages config directly
    if not config.get("enabled"):
        return []
    
    # Greenhouse
    if "greenhouse" in config:
        for url in config["greenhouse"]:
            try:
                jobs = fetch_greenhouse_career(url)
                print(f"  {url}: {len(jobs)} remote jobs")
                all_jobs.extend(jobs)
                time.sleep(1)
            except Exception as e:
                print(f"[greenhouse_career] Error with {url}: {e}")
    
    # Lever
    if "lever" in config:
        for url in config["lever"]:
            try:
                jobs = fetch_lever_career(url)
                print(f"  {url}: {len(jobs)} remote jobs")
                all_jobs.extend(jobs)
                time.sleep(1)
            except Exception as e:
                print(f"[lever_career] Error with {url}: {e}")
    
    # Ashby
    if "ashby" in config:
        for url in config["ashby"]:
            try:
                jobs = fetch_ashby_career(url)
                print(f"  {url}: {len(jobs)} remote jobs")
                all_jobs.extend(jobs)
                time.sleep(1)
            except Exception as e:
                print(f"[ashby_career] Error with {url}: {e}")
    
    return all_jobs