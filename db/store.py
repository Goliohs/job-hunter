import sqlite3
from pathlib import Path
from typing import Optional
import json

DB_PATH = Path(__file__).parent.parent / "jobs.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    schema = Path(__file__).parent / "schema.sql"
    with get_conn() as conn:
        conn.executescript(schema.read_text())
    print(f"[db] Initialized at {DB_PATH}")


def job_exists(source: str, external_id: str) -> bool:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT 1 FROM jobs WHERE source=? AND external_id=?",
            (source, external_id),
        ).fetchone()
        return r is not None


def save_job(job: dict) -> bool:
    """Inserta o ignora si ya existe. Devuelve True si insertó nuevo."""
    with get_conn() as conn:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (source, external_id, title, company, description, url,
                    location, remote, tags, salary, posted_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job["source"],
                    job["external_id"],
                    job["title"],
                    job["company"],
                    job.get("description", ""),
                    job["url"],
                    job.get("location", ""),
                    job.get("remote", True),
                    json.dumps(job.get("tags", [])),
                    job.get("salary", ""),
                    job.get("posted_date", ""),
                ),
            )
            return conn.total_changes > 0
        except sqlite3.IntegrityError:
            return False


def update_match(source: str, external_id: str, score: int, reason: str, dealbreaker: str = ""):
    with get_conn() as conn:
        if score >= 60:
            conn.execute(
                """UPDATE jobs SET match_score=?, match_reason=?, dealbreaker_hit=?
                   WHERE source=? AND external_id=?""",
                (score, reason, dealbreaker, source, external_id),
            )
        else:
            conn.execute(
                """UPDATE jobs SET match_score=?, match_reason=?, dealbreaker_hit=?, status='rejected'
                   WHERE source=? AND external_id=?""",
                (score, reason, dealbreaker, source, external_id),
            )


def get_unmatched_jobs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE match_score=0 AND status='new'
               ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_top_jobs(limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE match_score >= 60 AND status='new'
               ORDER BY match_score DESC, created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        matched = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE match_score >= 60"
        ).fetchone()[0]
        high = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE match_score >= 80"
        ).fetchone()[0]
        applied = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='applied'"
        ).fetchone()[0]
        return {
            "total": total,
            "matched": matched,
            "high_match": high,
            "applied": applied,
        }


def log_run(source: str, fetched: int, saved: int, rejected: int, errors: str = ""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO run_log (source, total_fetched, total_saved, total_rejected, errors)
               VALUES (?,?,?,?,?)""",
            (source, fetched, saved, rejected, errors),
        )


def get_jobs_for_apply(min_score: int = 80, limit: int = 5) -> list[dict]:
    """Obtiene jobs para auto-aplicar (high match, status new).
    Prioritiza fuentes con ATS soportado (Greenhouse, Lever, Ashby)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM jobs
               WHERE match_score >= ? AND status='new'
               ORDER BY 
                   CASE WHEN source IN ('greenhouse_career', 'lever', 'ashby') THEN 0 ELSE 1 END,
                   match_score DESC, 
                   created_at DESC LIMIT ?""",
            (min_score, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_job(job_id: int) -> Optional[dict]:
    """Obtiene un job por ID."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def update_job(job_id: int, status: str, note: str = "") -> bool:
    """Actualiza el estado de un job y opcionalmente añade una nota."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ?",
            (status, job_id),
        )
        if note:
            conn.execute(
                "INSERT INTO job_notes (job_id, note, note_type) VALUES (?, ?, 'general')",
                (job_id, note),
            )
        return True


def add_job_note(job_id: int, note: str, note_type: str = "general") -> bool:
    """Añade una nota a un job."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO job_notes (job_id, note, note_type) VALUES (?, ?, ?)",
            (job_id, note, note_type),
        )
        return True


def get_job_notes(job_id: int) -> list[dict]:
    """Obtiene todas las notas de un job."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM job_notes WHERE job_id = ? ORDER BY created_at DESC",
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]
