"""Filtro que decide si un job merece ser guardado y analizado por LLM.

  Dos etapas:
   1) Pre-filtro heurístico (rápido, sin API call): revisa dealbreakers en title/description
   2) Filtro LLM (NIM): si pasa la etapa 1, envía a LLM para scoring semantic_match
   """
from filter.nim_client import analyze_job


def pre_filter(job: dict, profile: dict) -> tuple[bool, str]:
    """Pre-filtro heurístico. Devuelve (pasa, motivo_rechazo)."""
    text = (f"{job.get('title', '')} {job.get('description', '')}").lower()
    title_only = job.get("title", "").lower()

    if not text.strip():
        return False, "empty job text"

    # Dealbreakers hard (en el título es casi siempre fatal)
    for db in profile.get("dealbreakers", []):
        if db.lower() in title_only:
            return False, f"dealbreaker in title: {db}"

    # Dealbreakers en description general (3 strikes para requisitos de seniority)
    db_hits = []
    for db in profile.get("dealbreakers", []):
        if db.lower() in text:
            db_hits.append(db)
    if len(db_hits) >= 2:
        return False, f"dealbreakers: {', '.join(db_hits)}"

    # Si "senior" está separado de "junior" en el mismo texto (ej: "junior or senior")
    # evitamos falsos positivos
    years_required = None
    import re
    m = re.search(r"(\d+)\+?\s*years", text)
    if m:
        years_required = int(m.group(1))
        if years_required > profile["max_years_experience"] + 1:
            return False, f"requires {years_required}+ years (cap {profile['max_years_experience']})"

    # Si no es remote
    if profile.get("remote_only") and job.get("remote") is False:
        return False, "not remote"

    return True, ""


def filter_job(job: dict, profile: dict, config: dict) -> dict:
    """Pipeline completo: pre-filtro + LLM analysis."""
    passed, reason = pre_filter(job, profile)
    if not passed:
        return {
            "saved": False,
            "rejected": True,
            "reject_reason": reason,
            "match_score": 0,
            "reason": reason,
        }

    # Pasó pre-filtro → analiza con NIM
    result = analyze_job(job, profile, config)
    if not result:
        return {"saved": False, "rejected": False, "error": "llm_failed"}

    if result["match_score"] < config["filter"]["min_score"]:
        return {
            "saved": False,
            "rejected": True,
            "reject_reason": f"low score {result['match_score']}",
            "match_score": result["match_score"],
            "reason": result["reason"],
        }

    return {
        "saved": True,
        "rejected": False,
        "match_score": result["match_score"],
        "reason": result["reason"],
        "dealbreaker_hit": result["dealbreaker_hit"],
    }
