"""Email notification module for job alerts."""
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

# Load .env file at module level
from dotenv import load_dotenv
load_dotenv()

from db.store import get_conn, get_top_jobs, get_stats


class EmailNotifier:
    def __init__(self):
        # Read from environment variables lazily (in case .env is loaded after import)
        pass

    def _get_config(self):
        """Get config from environment variables (reads fresh each time)."""
        return {
            "smtp_host": os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
            "username": os.environ.get("SMTP_USER", ""),
            "password": os.environ.get("SMTP_PASS", ""),
            "from_email": os.environ.get("ALERT_FROM_EMAIL", os.environ.get("FROM_EMAIL", os.environ.get("SMTP_USER", ""))),
            "to_emails": [e.strip() for e in os.environ.get("ALERT_TO_EMAILS", os.environ.get("ALERT_EMAILS", "")).split(",") if e.strip()],
        }

    def is_configured(self) -> bool:
        cfg = self._get_config()
        return bool(cfg["username"] and cfg["password"] and cfg["to_emails"])

    def send_alert(self, subject: str, body: str, html_body: Optional[str] = None) -> bool:
        cfg = self._get_config()
        if not cfg["username"] or not cfg["password"] or not cfg["to_emails"]:
            print("[email] Not configured - skipping notification")
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = cfg["from_email"]
            msg["To"] = ", ".join(cfg["to_emails"])

            msg.attach(MIMEText(body, "plain"))
            if html_body:
                msg.attach(MIMEText(html_body, "html"))

            context = ssl.create_default_context()
            with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
                server.starttls(context=context)
                server.login(cfg["username"], cfg["password"])
                server.send_message(msg)

            print(f"[email] Alert sent to {len(cfg['to_emails'])} recipients")
            return True
        except Exception as e:
            print(f"[email] Failed to send alert: {e}")
            return False

    def send_daily_digest(self) -> bool:
        """Send daily digest of new high-match jobs."""
        conn = get_conn()
        
        # Get jobs from last 24h with high match
        jobs = conn.execute("""
            SELECT * FROM jobs 
            WHERE match_score >= 80 
            AND status = 'new'
            AND datetime(created_at) >= datetime('now', '-1 day')
            ORDER BY match_score DESC, created_at DESC
            LIMIT 20
        """).fetchall()

        if not jobs:
            return True  # Nothing to report

        subject = f"🎯 Job Hunter: {len(jobs)} new high-match jobs"
        
        body = f"""Job Hunter Daily Digest - {datetime.now().strftime('%Y-%m-%d')}

Found {len(jobs)} new high-match jobs (≥80 score):

"""
        html_body = f"""<html><body>
<h2>Job Hunter Daily Digest - {datetime.now().strftime('%Y-%m-%d')}</h2>
<p>Found <strong>{len(jobs)}</strong> new high-match jobs (≥80 score):</p>
<ul>
"""
        
        for job in jobs:
            body += f"- [{job['match_score']}] {job['title']} @ {job['company']} ({job['source']})\n  {job['url']}\n  {job.get('match_reason', '')[:100]}\n\n"
            
            html_body += f"""<li>
                <strong>[{job['match_score']}] {job['title']}</strong> @ {job['company']} 
                <span style="color: #666;">({job['source']})</span><br>
                <a href="{job['url']}">View Job</a><br>
                <small>{job.get('match_reason', '')[:150]}</small>
            </li>"""

        body += "\n---\nJob Hunter Bot\nRun ./run.sh to process new jobs"
        html_body += """</ul><hr><p><small>Job Hunter Bot • <a href="http://localhost:5001">Dashboard</a></small></p></body></html>"""

        return self.send_alert(subject, body, html_body)

    def send_high_match_alert(self, job: dict) -> bool:
        """Send immediate alert for a single high-match job."""
        subject = f"🚨 HIGH MATCH ({job['match_score']}): {job['title']} @ {job['company']}"
        
        body = f"""High-match job alert!

Title: {job['title']}
Company: {job['company']}
Score: {job['match_score']}/100
Source: {job['source']}
URL: {job['url']}

Reason: {job.get('match_reason', 'N/A')}

Apply: {job['url']}
Dashboard: http://localhost:5001

---
Job Hunter Bot
"""
        html_body = f"""<html><body>
<h2>🚨 High Match Alert: {job['match_score']}/100</h2>
<h3>{job['title']} @ {job['company']}</h3>
<p><strong>Source:</strong> {job['source']}<br>
<strong>Reason:</strong> {job.get('match_reason', 'N/A')}</p>
<p><a href="{job['url']}" style="background:#2563eb;color:white;padding:10px 20px;text-decoration:none;border-radius:4px;">Apply Now</a></p>
<p><a href="http://localhost:5001">View Dashboard</a></p>
<hr><small>Job Hunter Bot</small>
</body></html>"""

        return self.send_alert(subject, "", html_body)


def send_new_job_alert(job: dict) -> bool:
    """Convenience function for immediate alerts."""
    notifier = EmailNotifier()
    return notifier.send_high_match_alert(job)


def send_digest() -> bool:
    """Convenience function for daily digest."""
    notifier = EmailNotifier()
    return notifier.send_daily_digest()