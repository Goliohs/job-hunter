"""Detector de ATS (Applicant Tracking System) por URL."""
from urllib.parse import urlparse
from enum import Enum


class ATSType(Enum):
    LEVER = "lever"
    GREENHOUSE = "greenhouse"
    ASHBY = "ashby"
    WORKABLE = "workable"
    BREEZY = "breezy"
    UNKNOWN = "unknown"


ATS_PATTERNS = {
    ATSType.LEVER: [
        "lever.co",
        "jobs.lever.co",
    ],
    ATSType.GREENHOUSE: [
        "greenhouse.io",
        "boards.greenhouse.io",
        "grnh.se",
    ],
    ATSType.ASHBY: [
        "ashbyhq.com",
        "jobs.ashbyhq.com",
    ],
    ATSType.WORKABLE: [
        "workable.com",
        "apply.workable.com",
    ],
    ATSType.BREEZY: [
        "breezy.hr",
        "app.breezy.hr",
    ],
}


def detect_ats(url: str) -> ATSType:
    """Detecta el tipo de ATS por la URL."""
    parsed = urlparse(url)
    hostname = parsed.netloc.lower()
    path = parsed.path.lower()

    for ats_type, patterns in ATS_PATTERNS.items():
        for pattern in patterns:
            if pattern in hostname or pattern in path:
                return ats_type

    # Heurísticas adicionales por path
    if "/jobs/" in path and ("lever" in path or "greenhouse" in path or "ashby" in path):
        for ats_type in ATSType:
            if ats_type.value in path:
                return ats_type

    return ATSType.UNKNOWN


def get_ats_base_url(url: str) -> str:
    """Extrae la URL base del ATS para navegación."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


if __name__ == "__main__":
    test_urls = [
        "https://jobs.lever.co/company/role",
        "https://boards.greenhouse.io/company/jobs/123",
        "https://jobs.ashbyhq.com/company/abc",
        "https://apply.workable.com/j/123",
        "https://company.breezy.hr/p/role",
        "https://remoteok.com/remote-jobs/123",
    ]
    for url in test_urls:
        print(f"{url} -> {detect_ats(url).value}")