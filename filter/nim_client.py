"""Cliente NVIDIA NIM para análisis de JD y scoring de match."""
import os
import json
import httpx
from typing import Optional


NIM_API_KEY = os.environ.get("NIM_API_KEY", "")

# NIM acepta OpenAI-compatible chat completions
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def _build_prompt(job: dict, profile: dict) -> str:
    dealbreakers = "\n".join(f"- {d}" for d in profile.get("dealbreakers", []))
    preferences = "\n".join(f"- {p}" for p in profile.get("preferences", []))
    skills = ", ".join(profile.get("skills", []))
    target_roles = ", ".join(profile.get("target_roles", []))
    max_years = profile.get("max_years_experience", 15)

    return f"""You are an expert technical recruiter assistant. Analyze a job offer and score how well it matches a senior candidate profile.

CANDIDATE PROFILE:
- Senior DevOps Architect & Full-Stack Developer (10+ years experience)
- Target roles: {target_roles}
- Core skills: {skills}
- Max acceptable experience required: {max_years} years (senior/lead/principal welcome)
- Looking for: REMOTE / WORLDWIDE / ANYWHERE only
- Cannot do onsite, hybrid, or relocation-required roles
- Strong async work preference, written communication over calls
- Fluent English tech communication, native Spanish speaker
- Runs own infrastructure (bare metal, GPU nodes, homelab)
- Open to contract/freelance/consulting/part-time

DEALBREAKERS (auto-reject if any appear):
{dealbreakers}

PREFERENCES (boost score if mentioned):
{preferences}

JOB OFFER:
Title: {job.get('title', '')}
Company: {job.get('company', '')}
Location: {job.get('location', '')}
Description: {job.get('description', '')[:3000]}

Evaluate and respond ONLY with strict JSON (no markdown, no explanation):
{{
  "match_score": <0-100 integer>,
  "reason": "<2 sentence summary explaining the score>",
  "dealbreaker_hit": "<specific phrase from JD that triggered a dealbreaker, or empty string>",
  "remote_confirmed": <true/false>
}}

Scoring guidelines:
- 90-100: Perfect match — senior/lead/architect role, remote worldwide, strong stack overlap (Docker/K8s/AI/Infra), async-friendly, contract/freelance OK
- 70-89: Good match — senior role, remote, good stack overlap, minor gaps
- 50-69: Borderline — remote but stack mismatch or unclear seniority
- 0-49: Poor match — onsite/hybrid/relocation required, junior/entry-level, dealbreaker triggered"""


def analyze_job(job: dict, profile: dict, config: dict) -> Optional[dict]:
    """Analiza un job con NIM LLM. Devuelve {match_score, reason, dealbreaker_hit} o None."""
    api_key = os.environ.get(config["llm"]["api_key_env"], NIM_API_KEY)
    if not api_key:
        print("[nim] WARNING: NIM_API_KEY no configurada. ¿Está en el entorno?")
        return None

    prompt = _build_prompt(job, profile)
    payload = {
        "model": config["llm"]["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": config["llm"]["temperature"],
        "max_tokens": config["llm"]["max_tokens"],
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        resp = httpx.post(NIM_URL, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Limpieza: NIM a veces envuelve en ```json
        if "```" in content:
            start = content.find("{")
            end = content.rfind("}")
            content = content[start:end+1]

        result = json.loads(content)
        return {
            "match_score": int(result.get("match_score", 0)),
            "reason": result.get("reason", ""),
            "dealbreaker_hit": result.get("dealbreaker_hit", ""),
        }
    except httpx.HTTPStatusError as e:
        print(f"[nim] HTTP error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except json.JSONDecodeError as e:
        print(f"[nim] JSON parse error: {e}")
        print(f"[nim] Raw output: {content[:300] if 'content' in dir() else 'N/A'}")
        return None
    except Exception as e:
        print(f"[nim] Unexpected error: {e}")
        return None
