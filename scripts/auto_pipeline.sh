#!/usr/bin/env bash
# Auto-pipeline: espera a que termine el scoring y luego corre apply batches
# en auto (headed via Xvfb). Repite el apply para ir agotando la cola.
set -u
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE" || exit 1

source venv/bin/activate
set -a; source .env; set +a
mkdir -p logs

# 1. Esperar a que el scoring actual termine
echo "$(date '+%F %T') [pipeline] esperando a que termine el scoring..."
while pgrep -f "score_pending.py" >/dev/null 2>&1; do
    sleep 30
done
echo "$(date '+%F %T') [pipeline] scoring terminado"

# 2. Correr apply batches (headed, diversificado) hasta agotar aplicables
for i in 1 2 3 4 5; do
    echo "$(date '+%F %T') [pipeline] apply batch $i..."
    xvfb-run -a -s "-screen 0 1366x900x24" python3 -u main.py --apply >> logs/auto_pipeline.log 2>&1
    rc=$?
    echo "$(date '+%F %T') [pipeline] apply batch $i terminado (rc=$rc)"
    sleep 10
done

echo "$(date '+%F %T') [pipeline] pipeline completado"