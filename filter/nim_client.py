"""Cliente LLM para análisis de JD y scoring de match.

Backends:
  - NVIDIA NIM (OpenAI-compatible)  — primary
  - Ollama local (fallback cuando NIM está rate-limited o caído)
"""
import os
import json
import re
import httpx
from typing import Optional


NIM_API_KEY = os.environ.get("NIM_API_KEY", "")

# NIM acepta OpenAI-compatible chat completions
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-tuned:latest")


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


def _parse_result_content(content: str) -> Optional[dict]:
    """Extrae el JSON {match_score, reason, dealbreaker_hit} de la respuesta LLM."""
    if not content:
        return None
    content = content.strip()
    # NIM a veces envuelve en ```json
    if "```" in content:
        start = content.find("{")
        end = content.rfind("}")
        content = content[start:end+1]

    result = None
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # Buscar el último objeto JSON válido (razonamiento + JSON final)
        for cand in reversed(re.findall(r"\{.*?\}", content, flags=re.DOTALL)):
            try:
                parsed = json.loads(cand)
                if "match_score" in parsed:
                    result = parsed
                    break
            except json.JSONDecodeError:
                continue
    if not isinstance(result, dict) or "match_score" not in result:
        print(f"[llm] No JSON encontrado. Raw: {content[:200]}")
        return None
    return {
        "match_score": int(result.get("match_score", 0)),
        "reason": result.get("reason", ""),
        "dealbreaker_hit": result.get("dealbreaker_hit", ""),
    }


def analyze_job_ollama(job: dict, profile: dict, config: dict) -> Optional[dict]:
    """Analiza un job con Ollama local (fallback sin rate limits)."""
    try:
        llm_cfg = config.get("llm", {})
        base_url = os.environ.get("OLLAMA_BASE_URL", llm_cfg.get("ollama_base_url", OLLAMA_BASE_URL))
        model = os.environ.get("OLLAMA_MODEL", llm_cfg.get("ollama_model", OLLAMA_MODEL))
        prompt = _build_prompt(job, profile)
        resp = httpx.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": llm_cfg.get("temperature", 0.3),
                    "num_predict": llm_cfg.get("max_tokens", 800),
                },
            },
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("response", "") or ""
        return _parse_result_content(content)
    except Exception as e:
        print(f"[ollama] Error: {e}")
        return None


def analyze_job(job: dict, profile: dict, config: dict) -> Optional[dict]:
    """Analiza un job con NIM LLM. Si falla o hay rate limit, cae a Ollama local."""
    # Leer SIEMPRE del entorno vivo (no de la constante de módulo, que se cachea al import)
    api_key = os.environ.get(config["llm"].get("api_key_env", "NIM_API_KEY"), "") or os.environ.get("NIM_API_KEY", "")
    if not api_key:
        print("[nim] WARNING: NIM_API_KEY no configurada. Usando Ollama local...")
        return analyze_job_ollama(job, profile, config)

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

    rate_limited = False
    try:
        resp = httpx.post(NIM_URL, json=payload, headers=headers, timeout=120)
        # Retry con backoff en rate limit (429) y sobrecarga (503)
        for attempt in range(2):
            if resp.status_code in (429, 503, 504):
                rate_limited = True
                wait = 5 * (attempt + 1)
                print(f"[nim] HTTP {resp.status_code}, retry en {wait}s...")
                import time
                time.sleep(wait)
                resp = httpx.post(NIM_URL, json=payload, headers=headers, timeout=120)
            else:
                break
        if resp.status_code in (429, 503, 504):
            rate_limited = True
            resp.raise_for_status()
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"].get("content") or ""
        if not content:
            # deepseek a veces responde solo reasoning_content (content=null)
            content = data["choices"][0]["message"].get("reasoning_content") or ""
        if not content:
            print("[nim] Empty content response, reintentando una vez...")
            resp = httpx.post(NIM_URL, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"].get("content") or data["choices"][0]["message"].get("reasoning_content") or ""

        result = _parse_result_content(content)
        if result:
            return result
    except httpx.HTTPStatusError as e:
        rate_limited = rate_limited or e.response.status_code in (429, 503, 504)
        print(f"[nim] HTTP error {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        print(f"[nim] Unexpected error: {e}")

    # Fallback: si NIM falló o hubo rate limit, usar Ollama local
    if rate_limited:
        print("[nim] Rate limit / sobrecarga → usando Ollama local")
    else:
        print("[nim] NIM falló → usando Ollama local")
    return analyze_job_ollama(job, profile, config)
