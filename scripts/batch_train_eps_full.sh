#!/usr/bin/env bash
# Run train_eps/run_pipeline.py for every date in logs/playbook_dates.txt.
# Skip dates whose models_eps/<DATE>/predictions_results.csv already exists.
# On per-date failure, log and continue to next date.
set -u

cd "$(dirname "$0")/.."

DATES_FILE="logs/playbook_dates.txt"
SUMMARY="logs/train_eps_full_summary.txt"

ok=0; skipped=0; failed=0
failed_dates=()

start_ts=$(date -Iseconds)
echo "[batch] start=$start_ts"
echo

while read -r d; do
    [ -z "$d" ] && continue
    if [ -f "models_eps/$d/predictions_results.csv" ]; then
        echo "[skip] $d (predictions_results.csv exists)"
        skipped=$((skipped+1))
        continue
    fi
    echo "============================================================"
    echo "[run]  $d  ($(date -Iseconds))"
    echo "============================================================"
    if venv/bin/python3 train_eps/run_pipeline.py --date "$d"; then
        echo "[ok]   $d"
        ok=$((ok+1))
    else
        echo "[FAIL] $d"
        failed=$((failed+1))
        failed_dates+=("$d")
    fi
done < "$DATES_FILE"

end_ts=$(date -Iseconds)
{
    echo "start=$start_ts"
    echo "end=$end_ts"
    echo "ok=$ok"
    echo "skipped=$skipped"
    echo "failed=$failed"
    if [ ${#failed_dates[@]} -gt 0 ]; then
        echo "failed_dates:"
        for d in "${failed_dates[@]}"; do echo "  $d"; done
    fi
} | tee "$SUMMARY"

[ "$failed" -eq 0 ]
