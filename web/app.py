from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import os
import sys
import subprocess
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import get_conn, get_stats, init_db, get_job, update_job, get_top_jobs, log_run, get_jobs_for_apply, add_job_note, get_job_notes

app = Flask(__name__, template_folder="templates")
DB_PATH = Path(__file__).parent.parent / "jobs.db"

run_lock = threading.Lock()
run_status = {"running": False, "output": "", "error": ""}


def get_jobs_query(status=None, score_min=None, source=None, search=None, page=1, per_page=20):
    conn = get_conn()
    where = ["1=1"]
    params = []

    if status:
        where.append("status = ?")
        params.append(status)
    if score_min is not None:
        where.append("match_score >= ?")
        params.append(score_min)
    if source:
        where.append("source = ?")
        params.append(source)
    if search:
        where.append("(title LIKE ? OR company LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%"] * 3)

    where_clause = " AND ".join(where)

    total = conn.execute(
        f"SELECT COUNT(*) FROM jobs WHERE {where_clause}", params
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT * FROM jobs
            WHERE {where_clause}
            ORDER BY match_score DESC, created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()

    jobs = [dict(r) for r in rows]
    return jobs, total


@app.route("/")
def index():
    stats = get_stats()
    return render_template("index.html", stats=stats)


@app.route("/jobs")
def jobs_list():
    status = request.args.get("status")
    score_min = request.args.get("score_min", type=int)
    source = request.args.get("source")
    search = request.args.get("search")
    page = request.args.get("page", 1, type=int)

    jobs, total = get_jobs_query(status, score_min, source, search, page)
    per_page = 20
    total_pages = (total + per_page - 1) // per_page
    return render_template(
        "jobs.html",
        jobs=jobs,
        total=total,
        status=status,
        score_min=score_min,
        source=source,
        search=search,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@app.route("/jobs/fragment")
def jobs_fragment():
    status = request.args.get("status")
    score_min = request.args.get("score_min", type=int)
    source = request.args.get("source")
    search = request.args.get("search")
    page = request.args.get("page", 1, type=int)

    if status == "all" or status == "":
        status = None

    jobs, total = get_jobs_query(status, score_min, source, search, page)
    per_page = 20
    total_pages = (total + per_page - 1) // per_page
    return render_template(
        "jobs_fragment.html",
        jobs=jobs,
        total=total,
        status=status,
        score_min=score_min,
        source=source,
        search=search,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@app.route("/jobs/<int:job_id>")
def job_detail(job_id):
    job = get_job(job_id)
    if not job:
        return "Job no encontrado", 404
    
    # Get notes for this job
    notes = get_job_notes(job_id)
    
    return render_template("job_detail.html", job=job, notes=notes)


@app.route("/jobs/<int:job_id>/quick-apply")
def job_quick_apply(job_id):
    job = get_job(job_id)
    if not job:
        return "Job no encontrado", 404

    from generator import generate_application_package
    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    package = generate_application_package(job, config["profile"])

    return render_template("quick_apply.html", job=job, package=package)


@app.route("/api/jobs/<int:job_id>/notes", methods=["POST"])
def api_add_note(job_id):
    job = get_job(job_id)
    if not job:
        return "Job no encontrado", 404

    note_type = request.form.get("note_type", "general")
    note_text = request.form.get("note", "").strip()
    if not note_text:
        return "", 400

    add_job_note(job_id, note_type, note_text)
    return f'''<div class="bg-gray-50 border border-gray-200 rounded-lg p-3">
                <div class="flex justify-between items-start mb-2">
                    <span class="text-xs text-gray-500 uppercase tracking-wide">{note_type}</span>
                    <span class="text-xs text-gray-400">just now</span>
                </div>
                <p class="text-gray-800 text-sm">{note_text}</p>
            </div>'''


@app.route("/api/run", methods=["POST"])
def api_run():
    global run_status
    if run_lock.locked():
        return jsonify({"success": False, "error": "Ya hay una corrida en progreso"})

    def run_pipeline():
        global run_status
        run_status = {"running": True, "output": "", "error": ""}
        try:
            env = os.environ.copy()
            result = subprocess.run(
                [sys.executable, "main.py"],
                cwd=Path(__file__).parent.parent,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )
            run_status["output"] = result.stdout
            run_status["error"] = result.stderr
        except subprocess.TimeoutExpired:
            run_status["error"] = "Timeout (10 min)"
        except Exception as e:
            run_status["error"] = str(e)
        finally:
            run_status["running"] = False

    thread = threading.Thread(target=run_pipeline)
    thread.start()
    return jsonify({"success": True, "message": "Pipeline iniciado"})


@app.route("/api/run/status")
def api_run_status():
    return jsonify(run_status)


@app.route("/api/jobs/<int:job_id>/status", methods=["POST"])
def api_job_status(job_id):
    new_status = request.form.get("status")
    valid = ("new", "viewed", "applied", "interviewing", "rejected", "offer")
    if new_status not in valid:
        return jsonify({"success": False, "error": "Estado inválido"}), 400

    conn = get_conn()
    conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
    conn.commit()

    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return jsonify({"success": False, "error": "Job no encontrado"}), 404

    job = dict(row)

    # Return just the select element for HTMX outerHTML swap
    options = ""
    for val, label in [("new", "Nuevo"), ("viewed", "Visto"), ("applied", "Aplicado"),
                       ("interviewing", "En proceso"), ("rejected", "Rechazado"), ("offer", "Oferta")]:
        selected = "selected" if job["status"] == val else ""
        options += f'<option value="{val}" {selected}>{label}</option>'

    return f'''<select name="status" hx-post="/api/jobs/{job_id}/status" hx-target="this" hx-swap="outerHTML"
            class="mt-1 w-full px-3 py-2 border rounded-lg">{options}</select>'''


@app.route("/api/jobs/<int:job_id>/generate-pdfs", methods=["POST"])
def api_generate_pdfs(job_id):
    job = get_job(job_id)
    if not job:
        return "<p class='text-red-600'>Job no encontrado</p>", 404

    import yaml
    from generator import generate_application_package, generate_application_pdfs

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    profile = config["profile"]
    package = generate_application_package(job, profile)
    files = generate_application_pdfs(job, package, profile)

    if files:
        html = "<div class='bg-green-50 border border-green-200 rounded-lg p-4'>"
        html += "<h3 class='font-semibold text-green-800 mb-2'>PDFs generados:</h3><ul class='space-y-1'>"
        for key, path in files.items():
            label = "Cover Letter" if "cover" in key else "CV"
            html += f"<li class='text-green-700'>✓ {label}: <code class='text-sm'>{path}</code></li>"
        html += "</ul></div>"
        return html
    else:
        return "<p class='text-red-600'>Error generando PDFs. Revisa que WeasyPrint esté instalado.</p>", 500


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)