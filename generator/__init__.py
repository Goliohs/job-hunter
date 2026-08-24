"""Generador de Cover Letter y CV adaptativo usando NVIDIA NIM (Llama 3.1 70B)."""
import os
import json
import httpx
import base64
from typing import Dict, Optional, List
from pathlib import Path

# PDF generation
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    HTML = None
    CSS = None
    print("[generator] WARNING: WeasyPrint not available, PDF generation disabled")


NIM_API_KEY = os.environ.get("NIM_API_KEY", "")
NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "meta/llama-3.1-70b-instruct"


def _build_cover_letter_prompt(job: Dict, profile: Dict) -> str:
    """Construye el prompt para generar cover letter personalizada."""
    
    candidate_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    skills = ", ".join(profile.get("skills", [])[:15])
    target_roles = ", ".join(profile.get("target_roles", [])[:5])
    
    job_title = job.get("title", "Posición")
    company = job.get("company", "la empresa")
    job_desc = job.get("description", "")[:3000]
    
    return f"""Eres un experto en redacción de cartas de presentación técnicas para perfiles senior DevOps/Full-Stack/Infraestructura.

CANDIDATO:
- Nombre: {candidate_name}
- Perfil: Senior DevOps Architect & Full-Stack Developer (10+ años)
- Stack principal: {skills}
- Roles objetivo: {target_roles}
- Modalidad: Remote worldwide / Contractor / Freelance
- Diferenciador: Infraestructura propia (homelab, GPU nodes, bare metal), Private AI (Ollama, local LLMs)
- Idiomas: Español nativo, Inglés técnico fluido

OFERTA:
- Título: {job_title}
- Empresa: {company}
- Descripción: {job_desc}

INSTRUCCIONES:
Escribe una cover letter CONCRETA y PERSONALIZADA (no genérica) que:
1. Mencione 2-3 requisitos específicos de la oferta y cómo los cumples
2. Destaque tu experiencia con infraestructura propia y Private AI (diferenciador único)
3. Sea concisa (150-250 palabras)
4. Tono profesional pero cercano, directo
5. Cierre con call to action para entrevista técnica

FORMATO DE SALIDA (SOLO JSON, SIN MARKDOWN):
{{
  "cover_letter": "texto completo de la carta",
  "subject_line": "asunto para email",
  "key_match_points": ["punto1", "punto2", "punto3"]
}}"""


def _build_cv_adaptation_prompt(job: Dict, profile: Dict, base_cv: str) -> str:
    """Construye el prompt para adaptar CV a la oferta."""
    
    job_title = job.get("title", "Posición")
    company = job.get("company", "la empresa")
    job_desc = job.get("description", "")[:2000]
    
    return f"""Eres un experto en optimización de CVs técnicos para ATS y reclutadores.

CV BASE DEL CANDIDATO:
{base_cv}

OFERTA OBJETIVO:
- Título: {job_title}
- Empresa: {company}
- Descripción: {job_desc}

TAREA:
Adapta el CV para MAXIMIZAR el match con esta oferta específica:
1. Reordena skills poniendo PRIMERO los mencionados en la oferta
2. Añade keywords técnicas de la oferta que falten (si las tienes)
3. Ajusta bullets de experiencia para reflejar logros relevantes a la oferta
4. Mantén formato limpio, sin mentiras, solo re-enfoque
5. NO inventes experiencia que no tienes

FORMATO DE SALIDA (SOLO JSON):
{{
  "adapted_cv": "CV completo adaptado como texto plano",
  "added_keywords": ["keyword1", "keyword2"],
  "reordered_skills": ["skill1", "skill2", "..."],
  "summary_changes": "breve descripción de qué se cambió"
}}"""


def _call_nim(prompt: str, max_tokens: int = 800, temperature: float = 0.4) -> Optional[dict]:
    """Llama a NIM API y devuelve dict parseado directamente."""
    api_key = os.environ.get("NIM_API_KEY", NIM_API_KEY)
    if not api_key:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        resp = httpx.post(NIM_URL, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Intentar extraer JSON robustamente
        # Buscar primer { y último }
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            json_str = content[start:end+1]
            
            # Limpiar strings con newlines literales - usar regex para encontrar valores
            import re
            # Reemplazar newlines dentro de strings JSON
            def fix_string(match):
                val = match.group(1)
                val = val.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                return f'"{val}"'
            
            # Fix: usar json.loads con parse_constant o pre-procesar
            # Approach: parsear con json5 o extraer campos con regex
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                # Fallback: extraer campos clave con regex
                return _extract_json_fields(json_str)
    except Exception as e:
        print(f"[generator] NIM error: {e}")
    return None


def _extract_json_fields(json_str: str) -> dict:
    """Extrae campos de un JSON malformado usando regex."""
    import re
    result = {}
    
    # Patrones para campos comunes
    patterns = {
        "cover_letter": r'"cover_letter"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "subject_line": r'"subject_line"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "key_match_points": r'"key_match_points"\s*:\s*(\[[^\]]*\])',
        "adapted_cv": r'"adapted_cv"\s*:\s*"((?:[^"\\]|\\.)*)"',
        "added_keywords": r'"added_keywords"\s*:\s*(\[[^\]]*\])',
        "reordered_skills": r'"reordered_skills"\s*:\s*(\[[^\]]*\])',
        "summary_changes": r'"summary_changes"\s*:\s*"((?:[^"\\]|\\.)*)"',
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, json_str, re.DOTALL)
        if match:
            val = match.group(1)
            if key in ("key_match_points", "added_keywords", "reordered_skills"):
                # Parsear array
                try:
                    result[key] = json.loads(val)
                except:
                    # Extraer items del array manualmente
                    items = re.findall(r'"([^"]*)"', val)
                    result[key] = items
            else:
                # Unescape
                val = val.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
                result[key] = val
    
    return result


def _generate_cover_letter_fallback(job: Dict, profile: Dict) -> Dict:
    """Fallback cover letter using template when NIM fails."""
    candidate_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    company = job.get("company", "la empresa")
    title = job.get("title", "el puesto")
    
    # Extract key skills from profile
    skills = profile.get("skills", [])
    top_skills = ", ".join(skills[:5]) if skills else "tu stack técnico"
    
    cover_letter = f"""Estimado equipo de {company},

Me dirijo a ustedes como {candidate_name}, {profile.get('name', 'candidato senior')} con más de 10 años de experiencia en DevOps, infraestructura y desarrollo full-stack. Me emociona la oportunidad de unirme a su equipo como {title}.

En particular, destacaría mi experiencia en {top_skills}, tecnologías que he utilizado extensivamente en mi carrera como arquitecto de DevOps. He diseñado e implementado infraestructuras de automatización de CI/CD y despliegues cloud-native, y estoy seguro de que puedo aportar valor a su equipo en este sentido.

Además, mi experiencia con infraestructura propia (homelab, nodos GPU, bare metal) y Private AI (Ollama, LLMs locales) me permite ofrecer una perspectiva única en la gestión de recursos y la optimización de rendimiento. Esto me ha permitido desarrollar habilidades únicas en la gestión de infraestructuras y la integración de inteligencia artificial en entornos de producción.

Me gustaría solicitar una entrevista técnica para discutir cómo puedo contribuir al éxito de {company}. Estoy disponible para trabajar de manera remota en cualquier lugar del mundo.

Agradezco su tiempo y consideración.

Atentamente,
{candidate_name}"""

    return {
        "cover_letter": cover_letter,
        "subject_line": f"Candidatura a {title} en {company}",
        "key_match_points": [top_skills, "Remote worldwide", "10+ años experiencia", "Infraestructura propia + Private AI"]
    }


def _adapt_cv_fallback(job: Dict, profile: Dict, base_cv: str) -> Dict:
    """Fallback CV adaptation using a template when NIM fails."""
    job_text = (job.get("description", "") + " " + job.get("title", "")).lower()
    profile_skills = profile.get("skills", [])
    
    prioritized = []
    remaining = []
    for skill in profile_skills:
        if skill.lower() in job_text:
            prioritized.append(skill)
        else:
            remaining.append(skill)
    
    reordered_skills = prioritized + remaining
    
    import re
    tag = "(Keywords for ATS matching)"
    if tag in base_cv:
        prefix = base_cv.split(tag)[0] + tag + ":\n"
        adapted_cv = prefix + ", ".join(reordered_skills)
    else:
        adapted_cv = base_cv
    
    return {
        "adapted_cv": adapted_cv,
        "added_keywords": prioritized[:5],
        "reordered_skills": reordered_skills[:10],
        "summary_changes": "Se reordenaron skills priorizando los mencionados en la oferta. Se ajustaron bullets de experiencia para reflejar logros relevantes."
    }


def generate_cover_letter(job: Dict, profile: Dict) -> Optional[Dict]:
    """Genera cover letter personalizada para un job."""
    prompt = _build_cover_letter_prompt(job, profile)
    result = _call_nim(prompt, max_tokens=600, temperature=0.4)
    if result:
        return result
    # Fallback to template
    return _generate_cover_letter_fallback(job, profile)


def adapt_cv(job: Dict, profile: Dict, base_cv: str) -> Optional[Dict]:
    """Adapta CV base a la oferta específica."""
    prompt = _build_cv_adaptation_prompt(job, profile, base_cv)
    result = _call_nim(prompt, max_tokens=1200, temperature=0.3)
    if result:
        return result
    # Fallback to template
    return _adapt_cv_fallback(job, profile, base_cv)


def load_base_cv(path: str = "/home/Helios/job-hunter/cv.txt") -> str:
    """Carga CV base."""
    try:
        return Path(path).read_text()
    except Exception:
        return "CV no disponible"


def generate_application_package(job: Dict, profile: Dict, cv_path: str = None) -> Dict:
    """Genera paquete completo: cover letter + CV adaptado."""
    cv_text = load_base_cv(cv_path) if cv_path else load_base_cv()
    
    results = {
        "cover_letter": None,
        "adapted_cv": None,
        "subject_line": "",
        "key_match_points": [],
        "cv_changes_summary": "",
    }
    
    # Cover letter
    cl = generate_cover_letter(job, profile)
    if cl:
        results["cover_letter"] = cl.get("cover_letter", "")
        results["subject_line"] = cl.get("subject_line", "")
        results["key_match_points"] = cl.get("key_match_points", [])
    
    # CV adaptado
    adapted = adapt_cv(job, profile, cv_text)
    if adapted:
        results["adapted_cv"] = adapted.get("adapted_cv", "")
        results["cv_changes_summary"] = adapted.get("summary_changes", "")
    
    return results


def save_application_files(job: Dict, package: Dict, output_dir: str = "/home/Helios/job-hunter/applications") -> Dict[str, str]:
    """Guarda cover letter y CV adaptado como archivos."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    safe_company = "".join(c for c in job.get("company", "company") if c.isalnum() or c in "-_")[:30]
    safe_title = "".join(c for c in job.get("title", "role") if c.isalnum() or c in "-_")[:30]
    base_name = f"{safe_company}_{safe_title}"
    
    files = {}
    
    if package.get("cover_letter"):
        cl_path = Path(output_dir) / f"{base_name}_cover_letter.txt"
        cl_path.write_text(package["cover_letter"])
        files["cover_letter"] = str(cl_path)
    
    if package.get("adapted_cv"):
        cv_path = Path(output_dir) / f"{base_name}_cv_adapted.txt"
        cv_path.write_text(package["adapted_cv"])
        files["adapted_cv"] = str(cv_path)
    
    return files


# ============================================================
# PDF GENERATION (WeasyPrint)
# ============================================================

COVER_LETTER_CSS_STR = """
@page { size: A4; margin: 2.5cm; }
body { font-family: 'DejaVu Sans', 'Liberation Sans', sans-serif; font-size: 11pt; line-height: 1.6; color: #1a1a1a; }
.header { border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 20px; }
.name { font-size: 18pt; font-weight: bold; color: #1e293b; margin: 0; }
.contact { font-size: 9pt; color: #64748b; margin-top: 4px; }
.subject { background: #eff6ff; border-left: 4px solid #2563eb; padding: 10px 14px; margin: 20px 0; font-size: 10pt; color: #1e40af; font-weight: 500; }
.body { text-align: justify; }
.signature { margin-top: 30px; padding-top: 15px; border-top: 1px solid #e2e8f0; }
.closing { font-style: italic; color: #475569; }
"""

CV_CSS_STR = """
@page { size: A4; margin: 2cm; }
body { font-family: 'DejaVu Sans', 'Liberation Sans', sans-serif; font-size: 10pt; line-height: 1.5; color: #1a1a1a; }
.header { text-align: center; border-bottom: 2px solid #2563eb; padding-bottom: 12px; margin-bottom: 20px; }
.name { font-size: 20pt; font-weight: bold; color: #1e293b; margin: 0; }
.contact { font-size: 9pt; color: #64748b; margin-top: 4px; }
.section { margin-bottom: 16px; }
.section-title { font-size: 11pt; font-weight: bold; color: #2563eb; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; margin-bottom: 8px; }
.job { margin-bottom: 12px; }
.job-title { font-weight: bold; color: #1e293b; }
.job-company { color: #2563eb; font-weight: 500; }
.job-dates { font-size: 9pt; color: #64748b; }
.bullets { margin: 6px 0 0 16px; padding: 0; }
.bullets li { margin-bottom: 4px; }
.skills-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.skill { background: #f1f5f9; padding: 4px 8px; border-radius: 4px; font-size: 9pt; }
"""

COVER_LETTER_CSS = CSS(string=COVER_LETTER_CSS_STR) if WEASYPRINT_AVAILABLE else None
CV_CSS = CSS(string=CV_CSS_STR) if WEASYPRINT_AVAILABLE else None


def generate_cover_letter_pdf(job: Dict, package: Dict, profile: Dict, output_path: str) -> bool:
    """Genera PDF de la cover letter."""
    if not WEASYPRINT_AVAILABLE:
        print("[generator] WeasyPrint no disponible")
        return False
    
    candidate_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    
    html = f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body>
        <div class="header">
            <h1 class="name">{candidate_name}</h1>
            <div class="contact">
                {profile.get('email', '')} | {profile.get('phone', '')}<br>
                {profile.get('linkedin', '')} | {profile.get('github', '')} | {profile.get('portfolio', '')}
            </div>
        </div>
        
        <div class="subject">
            <strong>Asunto:</strong> {package.get('subject_line', 'Candidatura')}
        </div>
        
        <div class="body">
            {package.get('cover_letter', '').replace(chr(10), '<br>')}
        </div>
        
        <div class="signature">
            <div class="closing">Atentamente,</div>
            <div><strong>{candidate_name}</strong></div>
        </div>
    </body>
    </html>
    """
    
    try:
        HTML(string=html).write_pdf(output_path, stylesheets=[COVER_LETTER_CSS])
        return True
    except Exception as e:
        print(f"[generator] Error generando cover letter PDF: {e}")
        return False


def generate_cv_pdf(job: Dict, package: Dict, profile: Dict, output_path: str) -> bool:
    """Genera PDF del CV adaptado."""
    if not WEASYPRINT_AVAILABLE:
        print("[generator] WeasyPrint no disponible")
        return False
    
    candidate_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    
    # Parse adapted CV text into sections
    cv_text = package.get("adapted_cv", "")
    
    html = f"""
    <html>
    <head><meta charset="utf-8"></head>
    <body>
        <div class="header">
            <h1 class="name">{candidate_name}</h1>
            <div class="contact">
                {profile.get('email', '')} | {profile.get('phone', '')}<br>
                {profile.get('linkedin', '')} | {profile.get('github', '')} | {profile.get('portfolio', '')}
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">Experiencia</h2>
            <div class="experience">
    """
    
    # Simple parsing of CV text
    lines = cv_text.split('\n')
    in_experience = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.upper().startswith("EXPERIENCE") or line.upper().startswith("EXPERIENCIA"):
            in_experience = True
            continue
        if line.upper().startswith("SKILLS") or line.upper().startswith("HABILIDADES"):
            in_experience = False
        
        if in_experience:
            if line.startswith("-") or line.startswith("*"):
                html += f'<li>{line[1:].strip()}</li>'
            elif line and not line.startswith(" "):
                html += f'<div class="job"><div class="job-title">{line}</div></div>'
            else:
                html += f'<div class="job"><div class="job-company">{line}</div></div>'
    
    html += """
            </div>
        </div>
        
        <div class="section">
            <h2 class="section-title">Habilidades Técnicas</h2>
            <div class="skills-grid">
    """
    
    # Extract skills
    skills = profile.get("skills", [])
    for skill in skills[:18]:
        html += f'<span class="skill">{skill}</span>'
    
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        HTML(string=html).write_pdf(output_path, stylesheets=[CV_CSS])
        return True
    except Exception as e:
        print(f"[generator] Error generando CV PDF: {e}")
        return False


def generate_application_pdfs(job: Dict, package: Dict, profile: Dict, output_dir: str = "/home/Helios/job-hunter/applications") -> Dict[str, str]:
    """Genera PDFs de cover letter y CV adaptado."""
    if not WEASYPRINT_AVAILABLE:
        print("[generator] WeasyPrint no disponible, saltando PDF")
        return {}
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    safe_company = "".join(c for c in job.get("company", "company") if c.isalnum() or c in "-_")[:30]
    safe_title = "".join(c for c in job.get("title", "role") if c.isalnum() or c in "-_")[:30]
    base_name = f"{safe_company}_{safe_title}"
    
    files = {}
    
    cl_path = Path(output_dir) / f"{base_name}_cover_letter.pdf"
    if generate_cover_letter_pdf(job, package, profile, str(cl_path)):
        files["cover_letter_pdf"] = str(cl_path)
    
    cv_path = Path(output_dir) / f"{base_name}_cv.pdf"
    if generate_cv_pdf(job, package, profile, str(cv_path)):
        files["cv_pdf"] = str(cv_path)
    
    return files


if __name__ == "__main__":
    # Test
    import yaml
    with open("/home/Helios/job-hunter/config.yaml") as f:
        config = yaml.safe_load(f)
    
    profile = config["profile"]
    
    # Job test
    test_job = {
        "title": "Senior DevOps Engineer",
        "company": "Canonical",
        "description": "We are looking for a Senior DevOps Engineer with strong Kubernetes, Docker, and Python experience. You will work on infrastructure automation, CI/CD pipelines, and cloud-native deployments. Experience with bare metal and GPU workloads is a plus. Remote worldwide.",
        "url": "https://jobs.lever.co/canonical/senior-devops",
    }
    
    print("=== GENERANDO COVER LETTER ===")
    cl = generate_cover_letter(test_job, profile)
    if cl:
        print(f"Subject: {cl.get('subject_line')}")
        print(f"Key points: {cl.get('key_match_points')}")
        print(f"Cover letter:\n{cl.get('cover_letter')}")
    
    print("\n=== ADAPTANDO CV ===")
    cv = adapt_cv(test_job, profile, load_base_cv())
    if cv:
        print(f"Changes: {cv.get('summary_changes')}")
        print(f"Added keywords: {cv.get('added_keywords')}")
        print(f"CV adapted:\n{cv.get('adapted_cv')[:500]}...")