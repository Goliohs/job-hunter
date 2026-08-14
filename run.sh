#!/usr/bin/env bash
# Wrapper para correr el bot fácilmente
# Uso:
#   ./run.sh        — pipeline completo (scrape + filtro LLM)
#   ./run.sh scrape — solo scraping (sin LLM)
#   ./run.sh stats  — solo muestra estadísticas
#   ./run.sh top    — muestra top 20 matches
#   ./run.sh apply       — semi-auto: llena form, tú resuelves CAPTCHA y haces click en Submit
#   ./run.sh apply 42    — semi-auto a un job específico por ID
#   ./run.sh auto        — auto-completo headless (experimental, falla con CAPTCHA)
#   ./run.sh cron   — loop continuo (cada 6h)
#   ./run.sh web    — inicia dashboard web en puerto 5001
#   ./run.sh all    — pipeline + dashboard web (background)
#   ./run.sh gen    — genera cover letter + CV adaptado para un job (test)

set -e
cd "$(dirname "$0")"

# Cargar .env si existe
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Activar venv
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

case "${1:-run}" in
    scrape)
        python3 main.py --scrape
        ;;
    stats)
        python3 main.py --stats
        ;;
    top)
        python3 main.py --top
        ;;
    apply)
        # Asegurar Xvfb corriendo para display virtual
        if ! pgrep -f "Xvfb :99" >/dev/null 2>&1; then
            echo "[apply] Arrancando Xvfb en :99..."
            nohup Xvfb :99 -screen 0 1280x720x24 -ac &>/dev/null & disown
            sleep 2
        fi
        export DISPLAY=:99
        # Si se pasa un ID, pasar como argumento a --semi-apply
        if [ -n "${2:-}" ]; then
            python3 main.py --semi-apply "$2"
        else
            python3 main.py --semi-apply
        fi
        ;;
    auto)
        # Auto-aplica headless (experimental, falla con CAPTCHA)
        python3 main.py --apply
        ;;
    cron)
        echo "[cron] Loop cada 6h. Ctrl+C para parar."
        while true; do
            python3 main.py
            echo "[cron] Esperando 6h..."
            sleep 21600
        done
        ;;
    web)
        echo "[web] Iniciando dashboard en http://localhost:5001"
        python3 web/app.py
        ;;
    all)
        # Pipeline completo + dashboard web en background
        echo "[all] Iniciando dashboard web en background..."
        python3 web/app.py &
        WEB_PID=$!
        echo "[all] Dashboard PID: $WEB_PID (http://localhost:5001)"
        
        # Esperar un poco a que levante
        sleep 3
        
        # Ejecutar pipeline
        python3 main.py
        
        # Mantener dashboard corriendo
        echo "[all] Pipeline completado. Dashboard sigue corriendo (PID: $WEB_PID)"
        echo "[all] Presiona Ctrl+C para detener todo"
        wait $WEB_PID
        ;;
    gen)
        # Test generator: python3 -c "from generator import ..."
        echo "[gen] Generando cover letter + CV de prueba..."
        python3 -c "
from generator import generate_cover_letter, adapt_cv, load_base_cv
import yaml
with open('config.yaml') as f:
    config = yaml.safe_load(f)
profile = config['profile']
test_job = {
    'title': 'Senior DevOps Engineer',
    'company': 'Canonical',
    'description': 'We are looking for a Senior DevOps Engineer with strong Kubernetes, Docker, and Python experience. You will work on infrastructure automation, CI/CD pipelines, and cloud-native deployments. Experience with bare metal and GPU workloads is a plus. Remote worldwide.',
    'url': 'https://jobs.lever.co/canonical/senior-devops',
}
print('=== COVER LETTER ===')
cl = generate_cover_letter(test_job, profile)
if cl:
    print(f'Subject: {cl.get(\"subject_line\")}')
    print(f'Key points: {cl.get(\"key_match_points\")}')
    print(cl.get('cover_letter'))
print()
print('=== ADAPTED CV ===')
cv = adapt_cv(test_job, profile, load_base_cv())
if cv:
    print(f'Changes: {cv.get(\"summary_changes\")}')
    print(f'Added keywords: {cv.get(\"added_keywords\")}')
    print(f'CV adapted (first 500 chars):')
    print(cv.get('adapted_cv', '')[:500])
"
        ;;
    run|*)
        python3 main.py
        ;;
esac