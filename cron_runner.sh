#!/usr/bin/env bash
# job-hunter cron runner
# Uso: cron_runner.sh [scrape|apply|all]
#   scrape: scrapea fuentes + filtra con LLM
#   apply:  auto-aplica a matches >= high_match_threshold (full-auto, headless)
#   all:    scrape + apply
#   xvfb-apply: apply en display virtual Xvfb (para fillers que rechazan headless)

set -u
MODE="${1:-all}"
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE" || exit 1

source venv/bin/activate
set -a
source .env 2>/dev/null
set +a

mkdir -p logs
LOG="logs/cron_$(date +%F).log"

# Lock global: nunca dos runs simultáneos
exec 9>/tmp/job-hunter-cron.lock
flock -n 9 || { echo "$(date '+%F %T') otro run activo, skip" >> "$LOG"; exit 0; }

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

log "=== cron run iniciado (mode=$MODE) ==="

run_pipeline() {
    log "--- scrape + filter ---"
    python3 main.py >> "$LOG" 2>&1
    log "--- pipeline terminado (rc=$?) ---"
}

run_apply() {
    log "--- auto-apply full-auto (headless) ---"
    python3 main.py --apply >> "$LOG" 2>&1
    log "--- apply terminado (rc=$?) ---"
}

run_apply_xvfb() {
    # Display virtual para fillers que rechazan headless puro
    if ! command -v xvfb-run >/dev/null 2>&1; then
        log "xvfb-run no instalado, fallback a headless"
        run_apply
        return
    fi
    log "--- auto-apply en Xvfb ---"
    xvfb-run -a -s "-screen 0 1366x900x24" python3 main.py --apply >> "$LOG" 2>&1
    log "--- apply xvfb terminado (rc=$?) ---"
}

case "$MODE" in
    scrape)     run_pipeline ;;
    apply)      run_apply_xvfb ;;
    xvfb-apply) run_apply_xvfb ;;
    all)        run_pipeline; run_apply_xvfb ;;
    *)          log "modo desconocido: $MODE"; exit 1 ;;
esac

log "=== cron run terminado ==="

# Rotación simple: mantener últimos 14 días
find logs -name "cron_*.log" -mtime +14 -delete 2>/dev/null
