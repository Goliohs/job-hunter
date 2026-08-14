"""Módulo de alertas Telegram para high matches."""
import os
import requests
from typing import Optional, Dict


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_telegram(message: str, parse_mode: str = "HTML") -> bool:
    """Envía un mensaje a Telegram. Devuelve True si OK."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    try:
        resp = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[telegram] Error enviando: {e}")
        return False


def format_job_alert(job: dict, result: Dict, config: dict) -> str:
    """Formatea una alerta de high match para Telegram."""
    title = job.get("title", "Sin título")
    company = job.get("company", "Desconocida")
    url = job.get("url", "")
    source = job.get("source", "")
    location = job.get("location", "Remote")
    score = result.get("match_score", 0)
    reason = result.get("reason", "")
    dealbreaker = result.get("dealbreaker_hit", "")

    lines = [
        f"🚀 <b>HIGH MATCH: {score}/100</b>",
        f"",
        f"💼 <b>{title}</b>",
        f"🏢 {company}",
        f"📍 {location}",
        f"🔗 <a href=\"{url}\">Ver oferta</a>",
        f"📊 Fuente: {source}",
        f"",
        f"🤖 <i>{reason}</i>",
    ]

    if dealbreaker:
        lines.append(f"⚠️ <b>Dealbreaker:</b> {dealbreaker}")

    return "\n".join(lines)


def alert_high_match(job: dict, result: Dict, config: dict) -> bool:
    """Envía alerta si el score >= high_match_threshold del config."""
    threshold = config.get("filter", {}).get("high_match_threshold", 80)
    score = result.get("match_score", 0)

    if score >= threshold:
        msg = format_job_alert(job, result, config)
        return send_telegram(msg)
    return False