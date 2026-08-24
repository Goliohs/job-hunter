# Job Hunter Bot

Remote job hunting bot: scrapes offers from 15+ sources, filters them with an LLM, generates a **job-tailored CV PDF**, and **applies automatically** on Greenhouse — including email verification.

## Features

- **Multi-source scraping**: Greenhouse, Lever, Ashby, LinkedIn, RemoteOK, WeWorkRemotely, Remotive, HackerNews, Wellfound, YC Jobs, and more
- **LLM filtering** (NVIDIA NIM / Llama 3.1 70B): 0-100 scoring against your profile
- **End-to-end Greenhouse auto-apply**:
  - Fills every field (including react-select comboboxes)
  - Uploads your CV as a **PDF tailored to each job posting**
  - Detects the OTP verification screen
  - **Reads the security code from your inbox via IMAP** (Zoho, Gmail, any IMAP)
  - Confirms — zero human intervention
- **Tracking**: every application gets its own folder with the posting, tailored CV, and result log
- **Semi-auto mode**: for broken forms or CAPTCHAs, the bot fills everything and waits for your final click
- **Learns**: saves form answers and reuses them across applications

## Quick start

### 1. Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

> `weasyprint` needs system libs (`pango`, `cairo`). If unavailable, the CV generator falls back to `fpdf2` automatically.

### 2. Your profile

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` -> `profile` section with your data (name, email, phone, LinkedIn, GitHub, skills, dealbreakers).

### 3. CV data for PDF generation

Create `~/.job-hunter/profile.yaml` with your structured CV (see `profile.yaml.example`).

### 4. Credentials (optional but recommended)

```bash
cp auto_apply/credentials.py.example auto_apply/credentials.py
```

Edit `auto_apply/credentials.py`:

- **IMAP (Zoho/Gmail)**: to read Greenhouse security codes. Zoho: Settings > Security > App Passwords (use the app password, not your main one). Also enable IMAP Access under Settings > Mail Accounts.
- **LinkedIn cookies**: for Easy Apply. Extract `li_at` and `JSESSIONID` from your browser.

### 5. LLM filter

```bash
export NIM_API_KEY="your_nvidia_api_key"
```

Free at [build.nvidia.com](https://build.nvidia.com).

## Usage

```bash
# Scrape all sources
python3 main.py --scrape

# Scrape + LLM filter
python3 main.py

# Stats and top matches
python3 main.py --stats
python3 main.py --top

# Full auto-apply (Greenhouse incl. email verification)
python3 main.py --apply

# Semi-auto: bot fills everything, you do the final click (broken forms/CAPTCHA)
python3 main.py --semi-apply
```

## How Greenhouse auto-apply works

```
1. Generates a CV PDF tailored to the posting (JD keywords -> skills reordered)
2. Fills the form (name, contact, comboboxes, label-matched questions)
3. Uploads the PDF
4. Clicks "Submit application"
5. Detects the security code screen (8 OTP boxes)
6. Reads the code from your inbox via IMAP (filtered by submit timestamp)
7. Types the code into the OTP boxes
8. Confirms -> "Application has been received"
```

## Project structure

```
config.yaml              # Your config (gitignored)
config.yaml.example      # Config template
auto_apply/
  credentials.py         # Your credentials (gitignored)
  credentials.py.example # Credentials template
  unified/               # Multi-ATS orchestrator (state machine)
    orchestrator.py      # ANALYZE->NAVIGATE->AUTH->FILL->VALIDATE->REVIEW->SUBMIT
    fillers_*.py         # Per-ATS fillers (Greenhouse, Lever, Ashby, LinkedIn...)
    zoho_imap.py         # Verification code reader
    session.py           # Persistent anti-detection browser
aggregator/              # Job board scrapers
filter/                  # Heuristic pre-filter + LLM matcher
generator/               # LLM cover letters
cv_generator.py          # Job-tailored CV PDFs
job_data.py              # Application tracking (~/.job-hunter/jobs/)
```

## Notes

- **Only applies to jobs you scraped and that scored >= 70** — review with `--top` before `--apply`
- `--apply` is fully autonomous on Greenhouse; use with judgment
- Every company's form varies: if something fails, the bot reports it and parks instead of sending garbage
- Rate limits are respected: the bot waits between applications

## License

MIT
