#!/bin/bash
# Monthly playbook orchestration: train_eps + strategies + backtester.
#
# Triggered by stock-playbook-run.timer on the 11th and 16th of every month at
# 04:00 (Asia/Taipei). The script self-gates against the canonical playbook
# calendar — only the canonical day for the current month actually runs;
# the other firing exits 0 immediately.
#
# Canonical playbook formula (train_eps/shared_config.py::playbook_run_date):
#   day = 16 if month in {5, 8, 11} else 11
#
# Manual override:
#   ./schedules/playbook_run.sh                 # auto-detect today; skip if not canonical
#   ./schedules/playbook_run.sh 2026-06-11      # force run for given playbook date

set -euo pipefail

cd "$(dirname "$0")/.."

TODAY="$(date +%Y-%m-%d)"
DATE_OVERRIDE="${1:-}"

# Compute DATE (this month's canonical playbook) + PREV_DATE (previous month's)
# via the project's canonical helper. Single source of truth.
mapfile -t DATES < <(venv/bin/python3 -c "
from train_eps.shared_config import playbook_run_date
import datetime as dt
override = '$DATE_OVERRIDE'
if override:
    d = dt.date.fromisoformat(override)
else:
    today = dt.date.today()
    d = dt.date.fromisoformat(playbook_run_date(today.year, today.month))
prev_y = d.year if d.month > 1 else d.year - 1
prev_m = d.month - 1 if d.month > 1 else 12
pd_iso = playbook_run_date(prev_y, prev_m)
print(d.isoformat())
print(pd_iso)
")
DATE="${DATES[0]}"
PREV_DATE="${DATES[1]}"

if [ -z "$DATE_OVERRIDE" ] && [ "$TODAY" != "$DATE" ]; then
    echo "Today ($TODAY) is not the canonical playbook date for this month ($DATE). Skipping."
    exit 0
fi

mkdir -p logs
LOG_FILE="logs/playbook_run_${DATE}_$(date +%Y%m%d_%H%M%S).log"

{
echo "========================================"
echo "Monthly playbook run"
echo "  DATE       = $DATE  (this cohort's playbook_date)"
echo "  PREV_DATE  = $PREV_DATE  (last cohort, used for step4 train_through)"
echo "  Started at = $(date)"
echo "========================================"

echo "[1/7] train_eps/run_pipeline.py --date $DATE"
venv/bin/python3 train_eps/run_pipeline.py --date "$DATE"

echo "[2/7] strategies/step1_prepare_data.py --date $DATE"
venv/bin/python3 strategies/step1_prepare_data.py --date "$DATE"

echo "[3/7] strategies/step2_finalize_strategy.py --date $DATE"
venv/bin/python3 strategies/step2_finalize_strategy.py --date "$DATE"

echo "[4/7] strategies/step3_analyze_feature_returns.py"
venv/bin/python3 strategies/step3_analyze_feature_returns.py

echo "[5/7] strategies/step4_train_selection_model.py --date $PREV_DATE  (train_through)"
venv/bin/python3 strategies/step4_train_selection_model.py --date "$PREV_DATE"

echo "[6/7] strategies/step5_score_and_publish.py --date $DATE"
venv/bin/python3 strategies/step5_score_and_publish.py --date "$DATE"

echo "[7/7] backtester/run_rolling.py --end-date $PREV_DATE --top-n 10"
venv/bin/python3 backtester/run_rolling.py \
    --start-date 2022-07-11 \
    --end-date "$PREV_DATE" \
    --top-n 10 --position-amount 100000

echo "========================================"
echo "Monthly playbook completed at $(date)"
echo "========================================"
} 2>&1 | tee -a "$LOG_FILE"
