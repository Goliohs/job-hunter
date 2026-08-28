"""Playwright-based scraper for JavaScript-heavy job sites."""
from typing import List, Dict
from playwright.sync_api import sync_playwright
import time
from urllib.parse import urljoin
import re


from pathlib import Path
def is_remote_job(text: str) -> bool:
    """Check if job text indicates remote work."""
    text_lower = text.lower()
    remote_keywords = ["remote", "anywhere", "worldwide", "global", "work from home", "wfh", "distributed", "telecommute"]
    exclude_keywords = ["hybrid", "onsite", "on-site", "office", "relocate", "relocation required", "must be in", "must be located"]
    
    has_remote = any(kw in text_lower for kw in remote_keywords)
    has_exclude = any(kw in text_lower for kw in exclude_keywords)
    
    return has_remote and not has_exclude


def fetch_with_playwright(url: str, browser, wait_selector: str = None, timeout: int = 60000) -> str:
    """Fetch page using Playwright and return HTML. Reuses browser instance."""
    page = browser.new_page(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
    )
    
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=15000)
        else:
            page.wait_for_timeout(5000)
        
        # Scroll to load more content
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        
        html = page.content()
        return html
    except Exception as e:
        print(f"[playwright] Error fetching {url}: {e}")
        return ""
    finally:
        page.close()


def get_browser():
    """Get a Playwright browser instance."""
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=True)
    return p, browser


def fetch_wellfound_jobs(max_pages: int = 3) -> List[Dict]:
    """Fetch Wellfound remote jobs using Playwright - extracts links from listing then fetches details."""
    all_jobs = []
    base_url = "https://wellfound.com/jobs"
    params = "?locations[]=Remote&roles[]=Software%20Engineer&roles[]=DevOps%20Engineer&roles[]=Data%20Engineer&roles[]=Backend%20Engineer&roles[]=Fullstack%20Engineer&roles[]=Platform%20Engineer&roles[]=SRE"
    
    p, browser = get_browser()
    
    try:
        for page_num in range(1, max_pages + 1):
            page_url = f"{base_url}{params}&page={page_num}" if page_num > 1 else f"{base_url}{params}"
            print(f"[wellfound-pw] Fetching page {page_num}")
            
            html = fetch_with_playwright(page_url, browser)
            if not html:
                continue
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            # Extract job links from listing page
            job_links = []
            for link in soup.select('a[href*="/jobs/"]'):
                href = link.get("href", "")
                if "/jobs/" in href and not any(x in href for x in ["/signup", "/login", "/company", "/search"]):
                    if not href.startswith("http"):
                        href = urljoin("https://wellfound.com", href)
                    job_links.append(href)
            
            # Deduplicate
            job_links = list(dict.fromkeys(job_links))
            
            print(f"[wellfound-pw] Found {len(job_links)} job links on page {page_num}")
            
            # Fetch details for each job
            page_jobs = 0
            for job_url in job_links[:20]:  # Limit to 20 per page
                try:
                    job_html = fetch_with_playwright(job_url, browser)
                    if not job_html:
                        continue
                    
                    job_soup = BeautifulSoup(job_html, "html.parser")
                    
                    # Check for Cloudflare
                    if "challenge" in job_html.lower() and "cloudflare" in job_html.lower():
                        print(f"[wellfound-pw] Cloudflare on {job_url}, skipping")
                        continue
                    
                    # Extract title
                    title_elem = job_soup.select_one('h1[data-test="job-title"], h1.job-title, h1')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    # Extract company
                    company = ""
                    company_links = job_soup.select('a[href*="/company/"]:not([href*="signup"]):not([href*="login"])')
                    for link in company_links:
                        text = link.get_text(strip=True)
                        if text and text.lower() not in ["company", "companies", "learn more"]:
                            company = text
                            break
                    
                    # Extract location
                    location_elem = job_soup.select_one('[data-test="job-location"], .job-location, .location')
                    location = location_elem.get_text(strip=True) if location_elem else ""
                    
                    # Full description
                    desc_elem = job_soup.select_one('[data-test="job-description"], .job-description, .description')
                    description = desc_elem.get_text(" ", strip=True) if desc_elem else job_soup.get_text(" ", strip=True)
                    
                    if not is_remote_job(description):
                        continue
                    
                    # Salary
                    salary_elem = job_soup.select_one('[data-test="job-salary"], .salary, .compensation')
                    salary = salary_elem.get_text(strip=True) if salary_elem else ""
                    
                    # Tags
                    tags = []
                    for tag in job_soup.select('[data-test="job-tag"], .tag, .skill-tag'):
                        t = tag.get_text(strip=True)
                        if t:
                            tags.append(t)
                    
                    external_id = job_url.split("/")[-1].split("?")[0]
                    
                    all_jobs.append({
                        "source": "wellfound",
                        "external_id": external_id,
                        "title": title,
                        "company": company,
                        "description": description[:5000],
                        "url": job_url,
                        "location": location or "Remote",
                        "remote": True,
                        "tags": tags,
                        "salary": salary,
                        "posted_date": "",
                    })
                    page_jobs += 1
                except Exception as e:
                    print(f"[wellfound-pw] Error fetching {job_url}: {e}")
                
                time.sleep(1)  # Be respectful
            
            print(f"[wellfound-pw] Page {page_num}: {page_jobs} remote jobs")
            
            if page_jobs == 0:
                break
            
            time.sleep(3)
    finally:
        browser.close()
        p.stop()
    
    return all_jobs


def fetch_yc_jobs(max_pages: int = 5) -> List[Dict]:
    """Fetch YC jobs using Playwright - YC has company pages with job sub-links."""
    all_jobs = []
    base_url = "https://www.ycombinator.com/jobs"
    
    p, browser = get_browser()
    
    try:
        for page_num in range(1, max_pages + 1):
            page_url = f"{base_url}?page={page_num}&remote=true" if page_num > 1 else f"{base_url}?remote=true"
            print(f"[yc_jobs-pw] Fetching page {page_num}")
            
            html = fetch_with_playwright(page_url, browser)
            if not html:
                continue
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            # Extract job links - they are under /companies/*/jobs/*
            job_links = []
            for link in soup.select('a[href*="/companies/"][href*="/jobs/"]'):
                href = link.get("href", "")
                if "/companies/" in href and "/jobs/" in href:
                    if not href.startswith("http"):
                        href = urljoin(base_url, href)
                    job_links.append(href)
            
            # Deduplicate
            job_links = list(dict.fromkeys(job_links))
            
            print(f"[yc_jobs-pw] Found {len(job_links)} job links on page {page_num}")
            
            # Fetch details for each job
            page_jobs = 0
            for job_url in job_links[:30]:  # Limit to 30 per page
                try:
                    job_html = fetch_with_playwright(job_url, browser)
                    if not job_html:
                        continue
                    
                    job_soup = BeautifulSoup(job_html, "html.parser")
                    
                    # Check for Cloudflare
                    if "challenge" in job_html.lower() and "cloudflare" in job_html.lower():
                        print(f"[yc_jobs-pw] Cloudflare on {job_url}, skipping")
                        continue
                    
                    # Extract title
                    title_elem = job_soup.select_one('h1[data-test="job-title"], h1.job-title, h1')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    # Extract company from URL or page
                    company = ""
                    company_elem = job_soup.select_one('[data-test="company-name"], .company-name')
                    if company_elem:
                        company = company_elem.get_text(strip=True)
                    else:
                        # Find the company link (not "Log in")
                        company_links = job_soup.select('a[href*="/companies/"]')
                        for link in company_links:
                            text = link.get_text(strip=True)
                            if text and text.lower() not in ["log in", "companies", "company"]:
                                company = text
                                break
                    
                    if not company:
                        # Extract from URL: /companies/COMPANY_NAME/jobs/...
                        parts = job_url.split("/")
                        for i, part in enumerate(parts):
                            if part == "companies" and i + 1 < len(parts):
                                company = parts[i + 1].replace("-", " ").title()
                                break
                    
                    # Extract location
                    location_elem = job_soup.select_one('[data-test="job-location"], .job-location, .location')
                    location = location_elem.get_text(strip=True) if location_elem else ""
                    
                    # Full description
                    desc_elem = job_soup.select_one('[data-test="job-description"], .job-description, .description, [class*="description"]')
                    description = desc_elem.get_text(" ", strip=True) if desc_elem else job_soup.get_text(" ", strip=True)
                    
                    if not is_remote_job(description):
                        continue
                    
                    # Tags
                    tags = []
                    for tag in job_soup.select('[data-test="job-tag"], .tag, .skill-tag'):
                        t = tag.get_text(strip=True)
                        if t:
                            tags.append(t)
                    
                    external_id = job_url.split("/")[-1].split("?")[0]
                    
                    all_jobs.append({
                        "source": "yc_jobs",
                        "external_id": external_id,
                        "title": title,
                        "company": company or "YC Company",
                        "description": description[:5000],
                        "url": job_url,
                        "location": location or "Remote",
                        "remote": True,
                        "tags": tags,
                        "salary": "",
                        "posted_date": "",
                    })
                    page_jobs += 1
                except Exception as e:
                    print(f"[yc_jobs-pw] Error fetching {job_url}: {e}")
                
                time.sleep(1)
            
            print(f"[yc_jobs-pw] Page {page_num}: {page_jobs} remote jobs")
            
            if page_jobs == 0:
                break
            
            time.sleep(3)
    finally:
        browser.close()
        p.stop()
    
    return all_jobs


def fetch_linkedin_jobs(search_urls: Dict[str, str], max_per_search: int = 50) -> Dict[str, List[Dict]]:
    """Fetch LinkedIn jobs using Playwright."""
    all_results = {}
    
    for search_name, url in search_urls.items():
        print(f"[linkedin-pw] Fetching {search_name}")
        
        html = fetch_with_playwright(url, wait_selector='li.job-result-card, div.job-card-container')
        if not html:
            all_results[search_name] = []
            continue
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        jobs = []
        
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
                link_url = link_elem.get("href", "") if link_elem else ""
                
                is_remote = "remote" in location.lower() or "anywhere" in location.lower() or "worldwide" in location.lower()
                
                external_id = ""
                if link_url:
                    match = re.search(r"/jobs/view/(\d+)", link_url) or re.search(r"/jobs/(\d+)", link_url)
                    if match:
                        external_id = match.group(1)
                
                jobs.append({
                    "source": "linkedin",
                    "external_id": external_id,
                    "title": title,
                    "company": company,
                    "description": f"LinkedIn: {title} at {company} ({location})",
                    "url": link_url,
                    "location": location,
                    "remote": is_remote,
                    "tags": [],
                    "salary": "",
                    "posted_date": "",
                })
                
                if len(jobs) >= max_per_search:
                    break
            except Exception:
                continue
        
        all_results[search_name] = jobs
        print(f"[linkedin-pw] {search_name}: {len(jobs)} jobs")
        
        time.sleep(3)
    
    return all_results


def fetch_company_careers(company: str, url: str, max_pages: int = 3) -> List[Dict]:
    """Fetch jobs from a company's career page using Playwright."""
    all_jobs = []
    
    p, browser = get_browser()
    
    try:
        for page_num in range(1, max_pages + 1):
            page_url = f"{url}?page={page_num}" if page_num > 1 else url
            print(f"[company_career:{company}] Fetching {page_url}")
            
            html = fetch_with_playwright(page_url, browser)
            if not html:
                continue
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            
            # Extract job links - try multiple patterns
            job_links = []
            for link in soup.select('a[href*="/jobs/"], a[href*="/careers/"], a[href*="/job/"]'):
                href = link.get("href", "")
                if any(x in href for x in ["/jobs/", "/careers/", "/job/"]):
                    if not href.startswith("http"):
                        href = urljoin(url, href)
                    job_links.append(href)
            
            # Deduplicate
            job_links = list(dict.fromkeys(job_links))
            
            print(f"[company_career:{company}] Found {len(job_links)} job links")
            
            if not job_links:
                break
            
            # Fetch details for each job
            page_jobs = 0
            for job_url in job_links[:30]:
                try:
                    job_html = fetch_with_playwright(job_url, browser)
                    if not job_html:
                        continue
                    
                    job_soup = BeautifulSoup(job_html, "html.parser")
                    
                    # Check for Cloudflare
                    if "challenge" in job_html.lower() and "cloudflare" in job_html.lower():
                        continue
                    
                    # Extract title
                    title_elem = job_soup.select_one('h1[data-test="job-title"], h1.job-title, h1[class*="title"], h1')
                    title = title_elem.get_text(strip=True) if title_elem else ""
                    
                    # Extract company
                    company_name = company
                    
                    # Extract location
                    location_elem = job_soup.select_one('[data-test="job-location"], .job-location, .location, [class*="location"]')
                    location = location_elem.get_text(strip=True) if location_elem else ""
                    
                    # Full description
                    desc_elem = job_soup.select_one('[data-test="job-description"], .job-description, .description, [class*="description"], main, article')
                    description = desc_elem.get_text(" ", strip=True) if desc_elem else job_soup.get_text(" ", strip=True)
                    
                    if not is_remote_job(description):
                        continue
                    
                    # Tags
                    tags = []
                    for tag in job_soup.select('[data-test="job-tag"], .tag, .skill-tag, [class*="tag"]'):
                        t = tag.get_text(strip=True)
                        if t and len(t) < 30:
                            tags.append(t)
                    
                    external_id = job_url.split("/")[-1].split("?")[0]
                    
                    all_jobs.append({
                        "source": "company_career",
                        "external_id": f"{company}-{external_id}",
                        "title": title,
                        "company": company_name,
                        "description": description[:5000],
                        "url": job_url,
                        "location": location or "Remote",
                        "remote": True,
                        "tags": tags,
                        "salary": "",
                        "posted_date": "",
                    })
                    page_jobs += 1
                except Exception as e:
                    print(f"[company_career:{company}] Error fetching {job_url}: {e}")
                
                time.sleep(1)
            
            print(f"[company_career:{company}] Page {page_num}: {page_jobs} remote jobs")
            
            if page_jobs == 0:
                break
            
            time.sleep(3)
    finally:
        browser.close()
        p.stop()
    
    return all_jobs


if __name__ == "__main__":
    import yaml
    with open(Path(__file__).resolve().parent.parent / "config.yaml") as f:
        config = yaml.safe_load(f)
    
    # Test Wellfound
    print("=== Testing Wellfound ===")
    jobs = fetch_wellfound_jobs(max_pages=2)
    print(f"Total: {len(jobs)}")
    for job in jobs[:3]:
        print(f"  - {job['title']} @ {job['company']} ({job['url']})")
    
    # Test YC Jobs
    print("\n=== Testing YC Jobs ===")
    jobs = fetch_yc_jobs(max_pages=2)
    print(f"Total: {len(jobs)}")
    for job in jobs[:3]:
        print(f"  - {job['title']} @ {job['company']} ({job['url']})")
    
    # Test Company Careers
    print("\n=== Testing Company Careers ===")
    jobs = fetch_company_careers("clickhouse", "https://clickhouse.com/careers", max_pages=2)
    print(f"Total: {len(jobs)}")
    for job in jobs[:3]:
        print(f"  - {job['title']} @ {job['company']} ({job['url']})")