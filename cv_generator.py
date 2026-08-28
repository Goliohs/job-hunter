#!/usr/bin/env python3
"""
CV Generator - Genera PDFs de CV adaptados por puesto.

Motores (en orden de preferencia):
1. WeasyPrint (HTML/CSS -> PDF bonito)
2. fpdf2 (fallback, PDF limpio)
3. txt (ultimo recurso)

Tailoring basico sin LLM:
- Extrae keywords del job description
- Reordena skills poniendo primero las relevantes
- Summary adaptado al titulo del rol
"""
import re
import yaml
from pathlib import Path
from datetime import datetime

PROFILE_YAML = Path("/home/youruser/.job-hunter/profile.yaml")
OUTPUT_DIR = Path(__file__).resolve().parent / "generated_cvs"

# Intentar motores
try:
    from weasyprint import HTML, CSS
    WEASYPRINT = True
except Exception:
    WEASYPRINT = False

try:
    from fpdf import FPDF
    FPDF2 = True
except Exception:
    FPDF2 = False


def load_profile() -> dict:
    with open(PROFILE_YAML) as f:
        return yaml.safe_load(f)


def extract_job_keywords(job: dict, top_n: int = 12) -> list:
    """Extrae keywords tecnicas del job description/title."""
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    # Keywords técnicas comunes en DevOps/infra
    candidates = [
        "kubernetes", "k8s", "docker", "terraform", "ansible", "linux",
        "python", "golang", "go", "typescript", "javascript", "react",
        "aws", "gcp", "azure", "postgres", "postgresql", "mysql", "redis",
        "mongodb", "clickhouse", "kafka", "prometheus", "grafana",
        "observability", "ci/cd", "gitlab", "github actions", "argo",
        "helm", "istio", "cilium", "sre", "reliability", "on-call",
        "incident", "postmortem", "slo", "sli", "gpu", "llm", "ai/ml",
        "ollama", "vllm", "bare metal", "high availability", "ha ",
        "distributed systems", "sql", "nosql", "networking", "vpn",
        "security", "devsecops", "gitops", "microservices", "api",
    ]
    found = [kw.strip() for kw in candidates if kw in text]
    return found[:top_n]


def tailor_profile(profile: dict, job: dict) -> dict:
    """Adapta el perfil al job: reordena skills, ajusta summary."""
    tailored = yaml.safe_load(yaml.safe_dump(profile))  # deep copy
    keywords = extract_job_keywords(job)
    job_title = job.get("title", "Engineer")

    # Summary adaptado al rol
    base_summary = tailored.get("summary", "").strip()
    kw_str = ", ".join(keywords[:5]) if keywords else "cloud-native infrastructure"
    tailored["summary"] = (
        f"Senior DevOps Architect applying for {job_title}. "
        f"{base_summary}"
    )

    # Reordenar skills: las que matchean keywords primero
    skills = tailored.get("skills", {})
    for category, items in skills.items():
        if not isinstance(items, list):
            continue
        def relevance(item):
            item_l = item.lower()
            return 0 if any(kw in item_l for kw in keywords) else 1
        skills[category] = sorted(items, key=relevance)

    tailored["_keywords"] = keywords
    tailored["_job_title"] = job_title
    return tailored


def _sanitize(name: str) -> str:
    return re.sub(r'[^\w-]', '_', name)[:40]


def generate_pdf_weasyprint(profile: dict, job: dict, out_path: Path) -> bool:
    """Genera PDF bonito con WeasyPrint."""
    try:
        kw = profile.get("_keywords", [])
        skills_html = ""
        for cat, items in profile.get("skills", {}).items():
            if not isinstance(items, list) or not items:
                continue
            cat_title = cat.replace("_", " ").title()
            lis = "".join(f"<li>{i}</li>" for i in items)
            skills_html += f'<div class="skill-cat"><h4>{cat_title}</h4><ul>{lis}</ul></div>'

        exp_html = ""
        for exp in profile.get("experience", []):
            achs = "".join(f"<li>{a}</li>" for a in exp.get("achievements", []))
            exp_html += f"""
            <div class="job">
              <div class="job-head"><b>{exp['role']}</b> @ {exp['company']}</div>
              <div class="meta">{exp.get('location','')} | {exp.get('start_date','')} – {exp.get('end_date','')}</div>
              <p>{exp.get('description','').strip()}</p>
              <ul>{achs}</ul>
              <div class="meta"><i>Tech: {exp.get('technologies','')}</i></div>
            </div>"""

        edu_html = "".join(
            f"<p><b>{e['degree']}</b> — {e['institution']} ({e.get('year','')})</p>"
            for e in profile.get("education", [])
        )
        cert_html = "".join(
            f"<li>{c['name']} ({c.get('issuer','')}, {c.get('year','')})</li>"
            for c in profile.get("certifications", [])
        )
        proj_html = ""
        for p in profile.get("projects", [])[:4]:
            proj_html += f"""
            <div class="job">
              <b>{p['name']}</b>
              <p>{p.get('description','').strip()[:300]}</p>
              <div class="meta"><i>{p.get('tech_stack','')}</i></div>
            </div>"""
        lang_html = " | ".join(
            f"{l['language']}: {l['proficiency']}" for l in profile.get("languages", [])
        )

        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head><body>
        <h1>{profile['full_name']}</h1>
        <div class="contact">
          {profile['email']} · {profile['phone']} · {profile['location']}<br>
          {profile['linkedin']} · {profile['github']} · {profile['portfolio']}
        </div>
        <h2>Summary</h2><p>{profile['summary']}</p>
        <h2>Technical Skills</h2><div class="skills">{skills_html}</div>
        <h2>Experience</h2>{exp_html}
        <h2>Education</h2>{edu_html}
        <h2>Certifications</h2><ul>{cert_html}</ul>
        <h2>Projects</h2>{proj_html}
        <h2>Languages</h2><p>{lang_html}</p>
        </body></html>"""

        css = """
        @page { size: A4; margin: 1.6cm 1.8cm; }
        body { font-family: 'DejaVu Sans', sans-serif; font-size: 9.5pt; line-height: 1.45; color: #1a1a1a; }
        h1 { font-size: 20pt; margin: 0 0 4pt; color: #0f172a; border-bottom: 2.5pt solid #2563eb; padding-bottom: 4pt; }
        .contact { font-size: 8.5pt; color: #475569; margin-bottom: 10pt; }
        h2 { font-size: 11pt; color: #2563eb; text-transform: uppercase; letter-spacing: 0.5pt;
             border-bottom: 0.7pt solid #cbd5e1; padding-bottom: 2pt; margin: 12pt 0 6pt; }
        p { margin: 3pt 0; text-align: justify; }
        .skills { display: flex; flex-wrap: wrap; }
        .skill-cat { width: 48%; margin-bottom: 6pt; }
        .skill-cat h4 { font-size: 9pt; margin: 0 0 2pt; color: #334155; }
        .skill-cat ul { margin: 0; padding-left: 12pt; font-size: 8.5pt; }
        .skill-cat li { margin: 1pt 0; }
        .job { margin-bottom: 8pt; }
        .job-head { font-size: 10pt; }
        .meta { font-size: 8pt; color: #64748b; margin: 2pt 0; }
        ul { margin: 3pt 0; padding-left: 14pt; }
        li { margin: 1.5pt 0; font-size: 9pt; }
        """
        HTML(string=html).write_pdf(str(out_path), stylesheets=[CSS(string=css)])
        return True
    except Exception as e:
        print(f"[cv_gen] WeasyPrint failed: {e}")
        return False


def generate_pdf_fpdf2(profile: dict, job: dict, out_path: Path) -> bool:
    """Fallback: PDF limpio con fpdf2."""
    try:
        pdf = FPDF(format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.set_margins(15, 12, 15)
        pdf.add_page()

        def clean(text: str) -> str:
            """Sanitiza a latin-1 (fuentes core de fpdf no soportan unicode)."""
            replacements = {
                "–": "-", "—": "-", "·": "|", "→": "->", "✓": "[ok]",
                """: '"', """: '"', "'": "'", "'": "'", "…": "...",
                "\u00a0": " ",
            }
            for k, v in replacements.items():
                text = text.replace(k, v)
            return text.encode("latin-1", "replace").decode("latin-1")

        def h1(text):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 20)
            pdf.cell(0, 10, clean(text), new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(37, 99, 235)
            pdf.set_line_width(0.8)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(3)

        def h2(text):
            pdf.set_x(pdf.l_margin)
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.set_text_color(37, 99, 235)
            pdf.cell(0, 7, clean(text).upper(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Helvetica", "", 9.5)

        def p(text, style="", size=9.5):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", style, size)
            pdf.multi_cell(0, 4.5, clean(text))

        # Header
        h1(profile["full_name"])
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(80, 80, 80)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 4, clean(f"{profile['email']} | {profile['phone']} | {profile['location']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 4, clean(f"{profile['linkedin']} | {profile['github']} | {profile['portfolio']}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

        h2("Summary")
        p(profile["summary"])

        h2("Technical Skills")
        for cat, items in profile.get("skills", {}).items():
            if isinstance(items, list) and items:
                p(f"{cat.replace('_',' ').title()}: " + ", ".join(items), size=8.5)

        h2("Experience")
        for exp in profile.get("experience", []):
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 5, clean(f"{exp['role']} @ {exp['company']}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 4, clean(f"{exp.get('location','')} | {exp.get('start_date','')} - {exp.get('end_date','')}"), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
            if exp.get("description"):
                p(exp["description"].strip(), size=9)
            for a in exp.get("achievements", []):
                p(f"- {a}", size=9)
            if exp.get("technologies"):
                p(f"Tech: {exp['technologies']}", style="I", size=8)
            pdf.ln(1.5)

        h2("Education")
        for e in profile.get("education", []):
            p(f"{e['degree']} - {e['institution']} ({e.get('year','')})", size=9)

        h2("Certifications")
        for c in profile.get("certifications", []):
            p(f"- {c['name']} ({c.get('issuer','')}, {c.get('year','')})", size=9)

        h2("Projects")
        for proj in profile.get("projects", [])[:4]:
            pdf.set_x(pdf.l_margin)
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.cell(0, 5, clean(proj["name"]), new_x="LMARGIN", new_y="NEXT")
            p(proj.get("description", "").strip()[:280], size=8.5)
            if proj.get("tech_stack"):
                p(f"Stack: {proj['tech_stack']}", style="I", size=8)

        h2("Languages")
        p(" | ".join(f"{l['language']}: {l['proficiency']}" for l in profile.get("languages", [])), size=9)

        pdf.output(str(out_path))
        return True
    except Exception as e:
        import traceback
        print(f"[cv_gen] fpdf2 failed: {e}")
        traceback.print_exc()
        return False


def generate_job_cv(job: dict, output_dir: Path = None) -> str:
    """
    Genera CV PDF adaptado a un job.
    Returns: ruta del PDF generado (o cv.txt como último recurso).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profile = load_profile()
    tailored = tailor_profile(profile, job)

    company = _sanitize(job.get("company", "company"))
    title = _sanitize(job.get("title", "role"))
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Preferir carpeta del job si existe
    out_dir = output_dir or OUTPUT_DIR
    out_path = out_dir / f"{company}_{title}_cv.pdf"

    engine = "weasyprint" if WEASYPRINT else ("fpdf2" if FPDF2 else None)
    ok = False
    if engine == "weasyprint":
        ok = generate_pdf_weasyprint(tailored, job, out_path)
    if not ok and FPDF2:
        ok = generate_pdf_fpdf2(tailored, job, out_path)

    if ok:
        print(f"[cv_gen] PDF generado ({engine}): {out_path}")
        return str(out_path)

    print("[cv_gen] WARNING: no PDF engine available, usando cv.txt")
    return str(Path(__file__).resolve().parent / "cv.txt")


if __name__ == "__main__":
    import sys
    job = {}
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        with open(sys.argv[1]) as f:
            job = yaml.safe_load(f)
    else:
        job = {
            "title": "Database Reliability Engineer",
            "company": "ClickHouse",
            "description": "Kubernetes PostgreSQL ClickHouse reliability SRE on-call incident Linux Python Go distributed systems",
        }
    path = generate_job_cv(job)
    print(f"CV: {path}")
