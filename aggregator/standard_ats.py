"""
Scrapers para plataformas ATS con formularios estándar y confiables:
Recruitee, Teamtailor, BreezyHR.

Estas plataformas tienen formularios consistentes y predecibles.
Workable se omite por rate limiting (429) y slugs de empresa inconsistentes.
"""
import httpx
import asyncio
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re

logger = logging.getLogger(__name__)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


async def fetch_recruitee_jobs(
    companies: List[str],
    keywords: List[str] = None,
    location: str = "Remote",
) -> List[Dict]:
    """
    Fetch jobs from Recruitee company career pages.
    
    Recruitee API: https://{company}.recruitee.com/api/offers
    """
    all_jobs = []
    
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for company in companies:
            try:
                await asyncio.sleep(1)  # Rate limit
                url = f"https://{company}.recruitee.com/api/offers"
                resp = await client.get(url, timeout=30)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                
                data = resp.json()
                offers = data.get("offers", [])
                
                for job in offers:
                    job_location = job.get("location", "")
                    is_remote = "remote" in job_location.lower() or job.get("remote", False)
                    
                    if location.lower() == "remote" and not is_remote:
                        continue
                    
                    all_jobs.append({
                        "source": "recruitee",
                        "external_id": str(job.get("id", "")),
                        "title": job.get("title", ""),
                        "company": company,
                        "description": job.get("description", ""),
                        "url": job.get("url", ""),
                        "location": job_location,
                        "remote": is_remote,
                        "tags": job.get("tags", []),
                        "salary": job.get("salary", ""),
                        "posted_date": job.get("created_at", ""),
                    })
                
                logger.info(f"[recruitee] {company}: {len(offers)} jobs")
                
            except Exception as e:
                logger.error(f"[recruitee] Error with {company}: {e}")
    
    return all_jobs


# Empresas conocidas que usan Recruitee (subdominios correctos)
RECRUITEE_COMPANIES = [
    "gitlab", "vercel", "supabase", "planetscale", "railway", "render",
    "flyio", "cloudflare", "mongodb", "redis", "hashicorp", "datadog",
    "elastic", "stripe", "cockroachdb", "timescale", "materialize",
    "tinybird", "airtable", "notion", "linear", "figma", "notion",
]


async def fetch_teamtailor_jobs(
    companies: List[str],
    keywords: List[str] = None,
    location: str = "Remote",
) -> List[Dict]:
    """
    Fetch jobs from Teamtailor company career pages.
    
    Teamtailor usa API GraphQL o REST en https://{company}.teamtailor.com/jobs
    """
    all_jobs = []
    
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for company in companies:
            try:
                await asyncio.sleep(1)  # Rate limit
                url = f"https://{company}.teamtailor.com/jobs"
                resp = await client.get(url, timeout=30)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                
                # Parse HTML para extraer jobs
                soup = BeautifulSoup(resp.text, "html.parser")
                
                # Teamtailor usa estructura específica
                job_cards = soup.find_all("a", class_=lambda c: c and "job" in c.lower())
                
                for card in job_cards:
                    job_url = card.get("href", "")
                    if not job_url:
                        continue
                    
                    # Extraer info del card
                    title = card.get_text(strip=True)
                    
                    # Intentar extraer location
                    location_text = card.get_text()
                    is_remote = "remote" in location_text.lower()
                    
                    all_jobs.append({
                        "source": "teamtailor",
                        "external_id": job_url.split("/")[-1],
                        "title": title,
                        "company": company,
                        "description": "",
                        "url": job_url if job_url.startswith("http") else f"https://{company}.teamtailor.com{job_url}",
                        "location": "Remote" if is_remote else "",
                        "remote": is_remote,
                        "tags": [],
                        "salary": "",
                        "posted_date": "",
                    })
                
                logger.info(f"[teamtailor] {company}: jobs found")
                
            except Exception as e:
                logger.error(f"[teamtailor] Error with {company}: {e}")
    
    return all_jobs


# Empresas conocidas que usan Teamtailor
TEAMTAILOR_COMPANIES = [
    "vercel", "supabase", "planetscale", "railway", "render",
    "flyio", "cloudflare", "mongodb", "redis", "hashicorp",
    "notion", "linear", "figma", "airbyte", "fivetran",
]


async def fetch_breezyhr_jobs(
    companies: List[str],
    keywords: List[str] = None,
    location: str = "Remote",
) -> List[Dict]:
    """
    Fetch jobs from BreezyHR company career pages.
    
    BreezyHR API: https://{company}.breezy.hr/api/v3/positions
    """
    all_jobs = []
    
    async with httpx.AsyncClient(headers=HEADERS, timeout=30, follow_redirects=True) as client:
        for company in companies:
            try:
                await asyncio.sleep(1)  # Rate limit
                url = f"https://{company}.breezy.hr/api/v3/positions"
                resp = await client.get(url, timeout=30)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                
                data = resp.json()
                positions = data.get("positions", [])
                
                for job in positions:
                    job_location = job.get("location", {}).get("name", "")
                    is_remote = "remote" in job_location.lower() or job.get("remote", False)
                    
                    if location.lower() == "remote" and not is_remote:
                        continue
                    
                    all_jobs.append({
                        "source": "breezyhr",
                        "external_id": str(job.get("id", "")),
                        "title": job.get("title", ""),
                        "company": company,
                        "description": job.get("description", ""),
                        "url": job.get("url", ""),
                        "location": job_location,
                        "remote": is_remote,
                        "tags": job.get("tags", []),
                        "salary": "",
                        "posted_date": job.get("created_at", ""),
                    })
                
                logger.info(f"[breezyhr] {company}: {len(positions)} jobs")
                
            except Exception as e:
                logger.error(f"[breezyhr] Error with {company}: {e}")
    
    return all_jobs


BREEZYHR_COMPANIES = [
    "github", "gitlab", "elastic", "mongodb", "redis", "hashicorp",
    "datadog", "vercel", "supabase", "planetscale", "railway", "render",
    "flyio", "cloudflare", "digitalocean", "netlify",
    "notion", "linear", "figma", "airbyte", "fivetran", "dbt",
    "prefect", "dagster", "temporalio", "confluent", "snowflake",
]


async def fetch_all_standard_ats_jobs(
    keywords: List[str] = None,
    location: str = "Remote",
) -> List[Dict]:
    """Fetch jobs from all standard ATS platforms."""
    all_jobs = []
    
    # Recruitee
    try:
        jobs = await fetch_recruitee_jobs(RECRUITEE_COMPANIES, keywords, location)
        all_jobs.extend(jobs)
    except Exception as e:
        logger.error(f"Recruitee fetch failed: {e}")
    
    # Teamtailor
    try:
        jobs = await fetch_teamtailor_jobs(TEAMTAILOR_COMPANIES, keywords, location)
        all_jobs.extend(jobs)
    except Exception as e:
        logger.error(f"Teamtailor fetch failed: {e}")
    
    # BreezyHR
    try:
        jobs = await fetch_breezyhr_jobs(BREEZYHR_COMPANIES, keywords, location)
        all_jobs.extend(jobs)
    except Exception as e:
        logger.error(f"BreezyHR fetch failed: {e}")
    
    return all_jobs


if __name__ == "__main__":
    import asyncio
    
    async def test():
        jobs = await fetch_all_standard_ats_jobs(
            keywords=["devops", "kubernetes", "python"],
            location="Remote",
        )
        print(f"Total jobs: {len(jobs)}")
        for job in jobs[:10]:
            print(f"  [{job['source']}] {job['title']} @ {job['company']} -> {job['url']}")
    
    asyncio.run(test())