#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.."

START_QUARTER="${1:-}"
END_QUARTER="${2:-}"

if [[ -z "$START_QUARTER" || -z "$END_QUARTER" ]]; then
    echo "Usage: $0 <START_QUARTER> <END_QUARTER>"
    echo "Example: $0 2021Q2 2025Q3"
    exit 1
fi

if ! [[ "$START_QUARTER" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    echo "Error: invalid START_QUARTER '$START_QUARTER' (expected YYYYQX)"
    exit 1
fi

if ! [[ "$END_QUARTER" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    echo "Error: invalid END_QUARTER '$END_QUARTER' (expected YYYYQX)"
    exit 1
fi

start_year="${START_QUARTER:0:4}"
start_q="${START_QUARTER:5:1}"
end_year="${END_QUARTER:0:4}"
end_q="${END_QUARTER:5:1}"

if (( 10#$start_year > 10#$end_year )) || { (( 10#$start_year == 10#$end_year )) && (( 10#$start_q > 10#$end_q )); }; then
    echo "Error: START_QUARTER must be <= END_QUARTER"
    exit 1
fi

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/backfill_xbrl_${START_QUARTER}_${END_QUARTER}_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Backfill Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Range: $START_QUARTER ~ $END_QUARTER" | tee -a "$LOG_FILE"
echo "FORCE_REPROCESS: ${FORCE_REPROCESS:-0}" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

year=$((10#$start_year))
quarter=$((10#$start_q))
end_year_num=$((10#$end_year))
end_q_num=$((10#$end_q))

while (( year < end_year_num || (year == end_year_num && quarter <= end_q_num) )); do
    target="${year}Q${quarter}"
    echo "" | tee -a "$LOG_FILE"
    echo "[RUN] $target" | tee -a "$LOG_FILE"

    if docker compose run --rm \
        -e FORCE_REPROCESS=${FORCE_REPROCESS:-0} \
        scraper-quarterly \
        python3 scraper/quarterly/fetch_xbrl.py --year "$year" --quarter "$quarter" 2>&1 | tee -a "$LOG_FILE"; then
        echo "[OK] $target" | tee -a "$LOG_FILE"
    else
        echo "[FAIL] $target" | tee -a "$LOG_FILE"
        exit 1
    fi

    quarter=$((quarter + 1))
    if (( quarter > 4 )); then
        quarter=1
        year=$((year + 1))
    fi
done

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Backfill Completed" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
