"""Flujo de aplicación semi-automática para ATS con CAPTCHA.

El bot llena todos los campos y sube el CV automáticamente.
El humano resuelve el CAPTCHA y hace click en Submit manualmente.
Después, el bot verifica el resultado y actualiza la DB.

Requiere Xvfb si no hay display X11/Wayland activo:
    Xvfb :99 -screen 0 1280x720x24 -ac & disown
    export DISPLAY=:99
"""
import os
import sys
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from auto_apply.base import CandidateProfile
from auto_apply.greenhouse import GreenhouseATS
from auto_apply.lever import LeverATS
from auto_apply.ashby import AshbyATS
from auto_apply.ats_detector import detect_ats, ATSType

HANDLERS = {
    ATSType.GREENHOUSE.value: GreenhouseATS,
    ATSType.LEVER.value: LeverATS,
    ATSType.ASHBY.value: AshbyATS,
}


def build_candidate_from_config(config: dict, cv_path: str, cover_letter_path: Optional[str] = None) -> CandidateProfile:
    """Construye CandidateProfile desde el config.yaml."""
    p = config["profile"]
    full = f"{p.get('first_name', 'Oscar')} {p.get('last_name', '')}".strip()
    return CandidateProfile(
        full_name=full,
        email=p.get("email", ""),
        phone=p.get("phone", ""),
        linkedin=p.get("linkedin", ""),
        github=p.get("github", ""),
        portfolio=p.get("portfolio", ""),
        location=p.get("location", "Remote Worldwide"),
        visa_status=p.get("visa_status", "No visa required for remote work"),
        notice_period=p.get("notice_period", "Immediate"),
        salary_expectation=p.get("salary_expectation", "Negotiable"),
        cv_path=cv_path,
        cover_letter_path=cover_letter_path,
    )


def semi_apply_job(job: dict, candidate: CandidateProfile, timeout: int = 600) -> Dict:
    """Aplica semi-auto a un job.

    1. Lanza browser headed (headless=False) bajo Xvfb
    2. El handler llena todos los campos automáticamente
    3. NO se hace click en Submit
    4. wait_for_human_submit() monitorea el estado de la página
    5. El humano resuelve CAPTCHA y hace click manual en Submit
    6. El bot detecta el resultado (URL change / success text / error)
    7. Actualiza el estado en la DB

    Requiere: DISPLAY=:99 con Xvfb corriendo.
    """
    ats_enum = detect_ats(job.get("url", ""))
    ats_name = ats_enum.value if ats_enum else "unknown"
    if not ats_enum or ats_name not in HANDLERS:
        return {
            "success": False,
            "ats": ats_name or "unknown",
            "message": f"ATS no soportado: {ats_name}",
        }

    # Asegurar que hay DISPLAY. Si no, intentar :99
    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = ":99"
        print("[semi-auto] DISPLAY no set. Asumiendo :99 (Xvfb)")

    if not os.path.exists(candidate.cv_path):
        return {
            "success": False,
            "ats": ats_name,
            "message": f"CV no encontrado: {candidate.cv_path}",
        }

    handler_class = HANDLERS[ats_name]
    handler = handler_class(profile=candidate, headless=False, semi_auto=True)

    print(f"\n{'='*60}")
    print(f"  SEMI-AUTO APPLY")
    print(f"  Job: {job.get('title', 'N/A')} @ {job.get('company', 'N/A')}")
    print(f"  ATS: {ats_name}")
    print(f"  URL: {job.get('url', '')}")
    print(f"  CV:  {candidate.cv_path}")
    print(f"{'='*60}")

    try:
        result = handler.apply(job["url"])
        result["ats"] = ats_name

        # Actualizar DB
        from db.store import get_conn
        if result.get("success"):
            with get_conn() as conn:
                conn.execute(
                    "UPDATE jobs SET status='applied', applied_date=datetime('now') "
                    "WHERE source=? AND external_id=?",
                    (job["source"], job["external_id"]),
                )
            print(f"\n  ✓[{ats_name}] Aplicación confirmada: {result.get('message', '')}")
        else:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE jobs SET status='failed' "
                    "WHERE source=? AND external_id=?",
                    (job["source"], job["external_id"]),
                )
            print(f"\n  ✗[{ats_name}] No aplicado: {result.get('message', '')}")

        return result
    except Exception as e:
        return {
            "success": False,
            "ats": ats_name,
            "message": f"Error semi_apply: {e}",
        }
    finally:
        try:
            handler.close_browser()
        except Exception:
            pass


def ensure_xvfb_running(display: str = ":99") -> bool:
    """Arranca Xvfb en el display dado si no está corriendo."""
    import subprocess

    # Verificar si ya hay Xvfb corriendo en :99
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"Xvfb {display}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    # Verificar socket X11
    socket_path = f"/tmp/.X11-unix/X{display.lstrip(':')}"
    if os.path.exists(socket_path):
        return True

    # Arrancar Xvfb
    try:
        subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1280x720x24", "-ac"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        import time
        time.sleep(2)
        print(f"[semi-auto] Xvfb arrancado en {display}")
        return True
    except FileNotFoundError:
        print("[semi-auto] ERROR: Xvfb no instalado. Instala con:")
        print("    sudo pacman -S xorg-server-xvfb   # Arch")
        print("    sudo apt install xvfb              # Debian/Ubuntu")
        return False
