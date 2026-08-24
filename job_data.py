"""
Job folder management and application data persistence (Proficiently-inspired).

Provides:
- Job folder structure: jobs/{company}-{title}-{date}/
- application-data.md loader/saver for reusable form answers
- Auto-save form answers after each application
"""
import os
import re
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

JOB_HUNTER_DIR = Path.home() / ".job-hunter"
JOBS_DIR = JOB_HUNTER_DIR / "jobs"
APPLICATION_DATA_FILE = JOB_HUNTER_DIR / "application-data.md"
PROFILE_FILE = JOB_HUNTER_DIR / "profile.md"
PREFERENCES_FILE = JOB_HUNTER_DIR / "preferences.md"


@dataclass
class JobApplication:
    """Represents a job application with all related files."""
    job_id: str
    company: str
    title: str
    ats: str
    url: str
    match_score: int
    folder: Path
    posting_file: Path
    resume_file: Path
    cover_letter_file: Path
    applied_file: Path
    
    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "company": self.company,
            "title": self.title,
            "ats": self.ats,
            "url": self.url,
            "match_score": self.match_score,
            "folder": str(self.folder),
            "created": datetime.now().isoformat(),
        }


class JobFolderManager:
    """Manages job application folders and files (Proficiently-inspired)."""
    
    def __init__(self):
        self.jobs_dir = JOBS_DIR
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
    
    def _sanitize(self, text: str) -> str:
        """Sanitize text for use in folder/file names."""
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s]+', '-', text.strip())
        return text[:50]
    
    def create_job_folder(self, job: dict) -> JobApplication:
        """Create folder structure for a job application."""
        company_safe = self._sanitize(job.get("company", "unknown"))
        title_safe = self._sanitize(job.get("title", "position"))
        date_str = datetime.now().strftime("%Y-%m-%d")
        job_id = f"{company_safe}-{title_safe}-{date_str}"
        
        folder = self.jobs_dir / job_id
        folder.mkdir(parents=True, exist_ok=True)
        
        app = JobApplication(
            job_id=job_id,
            company=job.get("company", ""),
            title=job.get("title", ""),
            ats=job.get("source", ""),
            url=job.get("url", ""),
            match_score=job.get("match_score", 0),
            folder=folder,
            posting_file=folder / "posting.md",
            resume_file=folder / "resume.md",
            cover_letter_file=folder / "cover-letter.md",
            applied_file=folder / "applied.md",
        )
        
        # Save job posting
        self._save_posting(app, job)
        
        return app
    
    def _save_posting(self, app: JobApplication, job: dict):
        """Save job posting to posting.md."""
        content = f"""# Job Posting: {job.get('title', '')} @ {job.get('company', '')}

**Company:** {job.get('company', '')}
**Title:** {job.get('title', '')}
**ATS:** {job.get('source', '')}
**URL:** {job.get('url', '')}
**Match Score:** {job.get('match_score', 0)}
**Location:** {job.get('location', '')}
**Remote:** {job.get('remote', False)}
**Salary:** {job.get('salary', '')}
**Posted:** {job.get('posted_date', '')}
**Scraped:** {datetime.now().isoformat()}

## Description

{job.get('description', '')}

## Tags
{', '.join(job.get('tags', []))}
"""
        app.posting_file.write_text(content)
    
    def save_resume(self, app: JobApplication, resume_content: str):
        """Save tailored resume."""
        app.resume_file.write_text(resume_content)
    
    def save_cover_letter(self, app: JobApplication, cover_letter: str):
        """Save cover letter."""
        app.cover_letter_file.write_text(cover_letter)
    
    def log_application(self, app: JobApplication, state: dict):
        """Log application result to applied.md."""
        content = f"""# Application Log

**Job:** {app.title} @ {app.company}
**ATS:** {app.ats}
**URL:** {app.url}
**Match Score:** {app.match_score}
**Applied:** {datetime.now().isoformat()}

## Status
- **Success:** {state.get('success', False)}
- **Status:** {state.get('status', 'unknown')}
- **Message:** {state.get('error_message', state.get('submit_response', ''))}

## Details
- **ATS:** {app.ats}
- **Match Score:** {app.match_score}
- **Human Approved:** {state.get('human_approved', False)}
- **Semi-auto:** {state.get('semi_auto', False)}

## Files Generated
- **Posting:** {app.posting_file.name}
- **Resume:** {app.resume_file.name if app.resume_file.exists() else 'N/A'}
- **Cover Letter:** {app.cover_letter_file.name if app.cover_letter_file.exists() else 'N/A'}

---
*Logged by Job Hunter on {datetime.now().isoformat()}*
"""
        app.applied_file.write_text(content)
    
    def get_all_applications(self) -> List[JobApplication]:
        """Get all applications from folders."""
        apps = []
        for folder in self.jobs_dir.iterdir():
            if folder.is_dir():
                applied_file = folder / "applied.md"
                if applied_file.exists():
                    # Parse applied.md to reconstruct
                    pass
        return apps


class ApplicationDataManager:
    """Manages application-data.md for reusable form answers (Proficiently-inspired)."""
    
    def __init__(self, filepath: Path = APPLICATION_DATA_FILE):
        self.filepath = filepath
        self.data = self._load()
        self.field_mappings = self._extract_field_mappings()
    
    def _load(self) -> str:
        """Load application data from file."""
        if self.filepath.exists():
            return self.filepath.read_text()
        return ""
    
    def save(self):
        """Save application data to file."""
        self.filepath.write_text(self.data)
        self.field_mappings = self._extract_field_mappings()
    
    def _extract_field_mappings(self) -> Dict[str, str]:
        """Extract field mappings from the Field Mappings section."""
        mappings = {}
        in_mappings = False
        for line in self.data.split('\n'):
            if line.strip().startswith('| Field Label Pattern'):
                in_mappings = True
                continue
            if in_mappings and line.strip().startswith('|---'):
                continue
            if in_mappings and line.strip().startswith('|'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    pattern = parts[1]
                    key = parts[2]
                    value = parts[3]
                    if pattern and key and value:
                        mappings[pattern.lower()] = value
            if in_mappings and not line.strip().startswith('|'):
                break
        return mappings
    
    def get_value_for_label(self, label: str) -> Optional[str]:
        """Get value for a form label using fuzzy matching."""
        label_lower = label.lower().strip()
        
        # Direct mapping check
        for pattern, value in self.field_mappings.items():
            if pattern in label_lower:
                return value
        
        # Check common patterns in the data sections
        return self._lookup_in_data(label_lower)
    
    def _lookup_in_data(self, label: str) -> Optional[str]:
        """Look up value in the data sections, usando el profile.yaml del usuario."""
        profile = self._load_user_profile()
        if not profile:
            return None

        if "name" in label and "first" in label:
            return profile.get("first_name")
        if "name" in label and "last" in label:
            return profile.get("last_name")
        if "full name" in label or "your name" in label:
            return f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or None
        if "email" in label:
            return profile.get("email")
        if "phone" in label or "teléfono" in label:
            return profile.get("phone")
        if "linkedin" in label:
            return profile.get("linkedin")
        if "github" in label:
            return profile.get("github")
        if "portfolio" in label or "website" in label or "personal site" in label:
            return profile.get("portfolio")
        if "location" in label or "current location" in label or "ciudad" in label:
            return profile.get("location")
        if "country" in label or "país" in label:
            return profile.get("country") or profile.get("location")
        if "sponsor" in label or "visa" in label or "work authoriz" in label:
            return profile.get("requires_sponsorship", "No")
        if "ai" in label and "consent" in label:
            return profile.get("ai_consent", "Yes")
        if "notice" in label or "availab" in label:
            return profile.get("notice_period", "Immediate")
        if "salary" in label or "compensation" in label or "salario" in label:
            return profile.get("salary_expectation", "Negotiable")

        # Respuestas de experiencia desde application-data.md (auto-aprendidas)
        return self.field_mappings.get(label)

    def _load_user_profile(self) -> dict:
        """Carga el perfil del usuario desde ~/.job-hunter/profile.yaml."""
        try:
            import yaml
            profile_yaml = JOB_HUNTER_DIR / "profile.yaml"
            if profile_yaml.exists():
                with open(profile_yaml) as f:
                    return yaml.safe_load(f) or {}
            # Fallback: config.yaml del repo
            config_yaml = Path(__file__).parent / "config.yaml"
            if config_yaml.exists():
                import yaml
                with open(config_yaml) as f:
                    cfg = yaml.safe_load(f) or {}
                    return cfg.get("profile", {})
        except Exception:
            pass
        return {}
    
    def save_answer(self, label: str, value: str, ats: str = ""):
        """Save a new answer to application-data.md."""
        if not label or not value:
            return
        
        # Check if already exists
        existing = self.get_value_for_label(label)
        if existing == value:
            return
        
        # Add to auto-saved section
        timestamp = datetime.now().strftime("%Y-%m-%d")
        entry = f"\n### {ats} ({timestamp})\n- **Question:** \"{label}\" → **{value}**\n"
        
        # Find the auto-saved section
        if "## Auto-Saved Answers" in self.data:
            insert_idx = self.data.find("## Auto-Saved Answers")
            # Find end of section (next ## or end of file)
            next_section = self.data.find("\n## ", insert_idx + 1)
            if next_section == -1:
                next_section = len(self.data)
            self.data = self.data[:next_section] + entry + self.data[next_section:]
        else:
            # Add section at end
            self.data += f"\n\n## Auto-Saved Answers{entry}"
        
        self.save()
    
    def get_value(self, key: str) -> Optional[str]:
        """Get a value by key desde el perfil del usuario."""
        profile = self._load_user_profile()
        if not profile:
            return None
        aliases = {
            "first_name": "first_name",
            "last_name": "last_name",
            "full_name": None,  # compuesto
            "email": "email",
            "phone": "phone",
            "linkedin": "linkedin",
            "github": "github",
            "portfolio": "portfolio",
            "location": "location",
            "visa_status": "visa_status",
            "notice_period": "notice_period",
            "salary_expectation": "salary_expectation",
        }
        if key == "full_name":
            return f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or None
        attr = aliases.get(key)
        if attr:
            return profile.get(attr)
        return self.field_mappings.get(key)


def load_profile() -> Dict:
    """Load profile from profile.md."""
    if PROFILE_FILE.exists():
        content = PROFILE_FILE.read_text()
        # Simple parsing - in reality use a proper markdown parser
        return {"raw": content}
    return {}


def load_preferences() -> Dict:
    """Load preferences from preferences.md."""
    if PREFERENCES_FILE.exists():
        try:
            return yaml.safe_load(PREFERENCES_FILE.read_text())
        except:
            pass
    return {}


# Global instances
job_folder_manager = JobFolderManager()
application_data = ApplicationDataManager()


if __name__ == "__main__":
    # Test
    print("Job Hunter Data Manager initialized")
    print(f"Jobs dir: {JOBS_DIR}")
    print(f"Application data: {APPLICATION_DATA_FILE}")
    print(f"Profile: {PROFILE_FILE}")
    print(f"Preferences: {PREFERENCES_FILE}")