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
# Host venv dependency: needs pandas_market_calendars (==5.2.4, matches the
# scraper pin) to resolve entry_date from the XTAI trading calendar so step2
# can run at 04:00 before the entry-day quote lands. See requirements-host.txt.
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

# entry_date = cutoff（= DATE − 1）之後第一個台股交易日，用 pandas_market_calendars
# 的 XTAI 日曆計算（涵蓋週末 + 國定假日/連假），完全不依賴 daily_quotes。讓 step2 在
# entry 當天清晨（04:00、entry 報價尚未進 DB）就能定出正確進場日、不必等資料。解析失敗
# （套件缺/日曆查詢出錯）則留空 → step2 退回原本的 daily_quotes 解析（可能因資料未到而 raise）。
echo "[2.5/7] resolve entry_date (XTAI calendar; first trading day after cutoff)"
ENTRY_DATE="$(venv/bin/python3 -c "
import sys
try:
    import pandas as pd
    import pandas_market_calendars as mcal
    from strategies.shared_config import cutoff_date_from_playbook
    cutoff = cutoff_date_from_playbook('$DATE')
    twse = mcal.get_calendar('XTAI')
    end = (pd.Timestamp(cutoff) + pd.Timedelta(days=30)).strftime('%Y-%m-%d')
    sched = twse.schedule(start_date=cutoff, end_date=end)
    entry = next(s for s in (t.strftime('%Y-%m-%d') for t in sched.index) if s > cutoff)
    print(entry)
except Exception as exc:
    sys.stderr.write(f'[entry_date] XTAI 解析失敗，step2 退回 daily_quotes 解析: {exc}\n')
")" || ENTRY_DATE=""
if [ -n "$ENTRY_DATE" ]; then
    echo "        entry_date = $ENTRY_DATE  (step2 will run with --entry-date)"
else
    echo "        entry_date = unresolved  (step2 falls back to daily_quotes lookup)"
fi

echo "[1/7] train_eps/run_pipeline.py --date $DATE"
venv/bin/python3 train_eps/run_pipeline.py --date "$DATE"

echo "[2/7] strategies/step1_prepare_data.py --date $DATE"
venv/bin/python3 strategies/step1_prepare_data.py --date "$DATE"

if [ -n "$ENTRY_DATE" ]; then
    echo "[3/7] strategies/step2_finalize_strategy.py --date $DATE --entry-date $ENTRY_DATE"
    venv/bin/python3 strategies/step2_finalize_strategy.py --date "$DATE" --entry-date "$ENTRY_DATE"
else
    echo "[3/7] strategies/step2_finalize_strategy.py --date $DATE"
    venv/bin/python3 strategies/step2_finalize_strategy.py --date "$DATE"
fi

echo "[4/7] strategies/step3_analyze_feature_returns.py"
venv/bin/python3 strategies/step3_analyze_feature_returns.py

echo "[5/7] strategies/step4_train_selection_model.py --date $PREV_DATE  (train_through)"
venv/bin/python3 strategies/step4_train_selection_model.py --date "$PREV_DATE"

echo "[6/7] strategies/step5_score_and_publish.py --date $DATE"
venv/bin/python3 strategies/step5_score_and_publish.py --date "$DATE"

echo "[7/7] backtester/run_rolling.py --end-date $PREV_DATE --top-n 25"
# top-n 25: within the seed-robust Sharpe plateau validated 2026-06. Across 4
# disjoint ensembles, monthly Sharpe climbs to a robust ~0.74 plateau over
# N≈20-26 (vs ~0.67 at N=10) before easing past ~26. See
# project_ensemble_validation_2026_06.
venv/bin/python3 backtester/run_rolling.py \
    --start-date 2022-07-11 \
    --end-date "$PREV_DATE" \
    --top-n 25 --position-amount 100000

echo "========================================"
echo "Monthly playbook completed at $(date)"
echo "========================================"
} 2>&1 | tee -a "$LOG_FILE"
