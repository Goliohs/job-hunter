#!/usr/bin/env python3
"""Quick Apply - Opens job URLs in browser with pre-filled application data."""
import os
import sys
import json
import webbrowser
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import get_conn, get_job, get_top_jobs
from generator import generate_application_package, load_base_cv, generate_application_pdfs


def generate_apply_url(job: dict, profile: dict) -> str:
    """Generate a pre-filled application URL for supported ATS platforms."""
    url = job.get("url", "")
    
    # Greenhouse
    if "greenhouse.io" in url or "boards.greenhouse.io" in url:
        # Greenhouse uses query params for some fields
        params = {
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "linkedin": profile.get("linkedin", ""),
            "github": profile.get("github", ""),
            "portfolio": profile.get("portfolio", ""),
        }
        # Filter empty values
        params = {k: v for k, v in params.items() if v}
        return f"{url}?{urllib.parse.urlencode(params)}"
    
    # Lever
    elif "lever.co" in url:
        params = {
            "name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "linkedin": profile.get("linkedin", ""),
            "github": profile.get("github", ""),
            "portfolio": profile.get("portfolio", ""),
        }
        params = {k: v for k, v in params.items() if v}
        return f"{url}?{urllib.parse.urlencode(params)}"
    
    # Workable
    elif "workable.com" in url:
        params = {
            "name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "linkedin": profile.get("linkedin", ""),
            "github": profile.get("github", ""),
        }
        params = {k: v for k, v in params.items() if v}
        return f"{url}?{urllib.parse.urlencode(params)}"
    
    # Ashby
    elif "ashbyhq.com" in url:
        params = {
            "name": f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip(),
            "email": profile.get("email", ""),
            "phone": profile.get("phone", ""),
            "linkedin": profile.get("linkedin", ""),
        }
        params = {k: v for k, v in params.items() if v}
        return f"{url}?{urllib.parse.urlencode(params)}"
    
    return url


def open_quick_apply(job_id: int, headless: bool = False):
    """Open job application in browser with pre-filled data."""
    conn = get_conn()
    job = get_job(job_id)
    
    if not job:
        print(f"Job {job_id} not found")
        return False
    
    # Load profile from config
    import yaml
    with open(Path(__file__).parent.parent / "config.yaml") as f:
        config = yaml.safe_load(f)
    profile = config.get("profile", {})
    
    # Generate application package
    package = generate_application_package(job, profile)
    cv_path = "/home/Helios/job-hunter/cv.txt"
    pdf_files = generate_application_pdfs(job, package, profile, cv_path)
    
    # Generate apply URL
    apply_url = generate_apply_url(job, profile)
    
    print(f"\n{'='*60}")
    print(f"QUICK APPLY: {job['title']} @ {job['company']}")
    print(f"{'='*60}")
    print(f"Match Score: {job.get('match_score', 'N/A')}")
    print(f"Source: {job.get('source', 'N/A')}")
    print(f"URL: {job['url']}")
    print(f"Apply URL: {apply_url}")
    print(f"\nGenerated files:")
    for k, v in pdf_files.items():
        print(f"  - {k}: {v}")
    print(f"\nMatch reasons: {job.get('match_reason', 'N/A')}")
    print(f"{'='*60}\n")
    
    # Open in browser
    try:
        webbrowser.open(apply_url)
        print(f"Opened in browser: {apply_url}")
    except Exception as e:
        print(f"Could not open browser: {e}")
        print(f"Manual URL: {apply_url}")
    
    # Print key info for manual copy-paste
    print("\n--- Quick Copy Data ---")
    print(f"Name: {profile.get('first_name', '')} {profile.get('last_name', '')}")
    print(f"Email: {profile.get('email', '')}")
    print(f"Phone: {profile.get('phone', '')}")
    print(f"LinkedIn: {profile.get('linkedin', '')}")
    print(f"GitHub: {profile.get('github', '')}")
    print(f"Portfolio: {profile.get('portfolio', '')}")
    print(f"Location: {profile.get('location', '')}")
    print(f"Visa Status: {profile.get('visa_status', '')}")
    print(f"Notice Period: {profile.get('notice_period', '')}")
    print(f"Salary Expectation: {profile.get('salary_expectation', '')}")
    print(f"Cover Letter:\n{profile.get('cover_letter', '')[:500]}...")
    
    # Mark as viewed
    conn = get_conn()
    conn.execute("UPDATE jobs SET status='viewed' WHERE source=? AND external_id=?", 
                 (job["source"], job["external_id"]))
    conn.commit()
    
    return True


def quick_apply_top(n: int = 5, min_score: int = 80):
    """Open top N unviewed high-match jobs in browser."""
    conn = get_conn()
    jobs = conn.execute(
        """SELECT * FROM jobs 
           WHERE match_score >= ? AND status = 'new'
           ORDER BY match_score DESC, created_at DESC LIMIT ?""",
        (min_score, n)
    ).fetchall()
    
    if not jobs:
        print(f"No new jobs with score >= {min_score}")
        return
    
    print(f"Opening top {len(jobs)} jobs (score >= {min_score})...")
    
    for job in jobs:
        open_quick_apply(job["id"])
    
    print(f"\nOpened {len(jobs)} job applications in browser")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Quick Apply - Open job applications with pre-filled data")
    parser.add_argument("job_id", nargs="?", type=int, help="Job ID to open")
    parser.add_argument("--top", type=int, help="Open top N unviewed high-match jobs")
    parser.add_argument("--min-score", type=int, default=80, help="Minimum match score for --top")
    
    args = parser.parse_args()
    
    if args.job_id:
        open_quick_apply(args.job_id)
    elif args.top:
        quick_apply_top(args.top, args.min_score)
    else:
        # Show top unviewed jobs
        conn = get_conn()
        jobs = conn.execute(
            """SELECT id, title, company, match_score, source, url 
               FROM jobs WHERE match_score >= 80 AND status='new'
               ORDER BY match_score DESC, created_at DESC LIMIT 10"""
        ).fetchall()
        
        if not jobs:
            print("No high-match unviewed jobs found")
            sys.exit(0)
        
        print("Top unviewed high-match jobs:")
        for i, job in enumerate(jobs, 1):
            print(f"  {i}. [{job['match_score']}] {job['title']} @ {job['company']} ({job['source']})")
            print(f"      {job['url']}")
        
        try:
            choice = input("\nEnter job number to open (or 'all' for all): ").strip()
            if choice.lower() == "all":
                quick_apply_top(len(jobs), 80)
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(jobs):
                    open_quick_apply(jobs[idx]["id"])
            else:
                print("Invalid choice")
        except KeyboardInterrupt:
            print("\nCancelled")