#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/xbrl_update_$(date +%Y%m%d_%H%M%S).log"

ARG1="${1:-}"
TARGET_DATE=""
TARGET_QUARTER=""

if [[ -z "$ARG1" ]]; then
    TARGET_DATE="$(date +%Y%m%d)"
elif [[ "$ARG1" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    TARGET_QUARTER="$ARG1"
elif [[ "$ARG1" =~ ^[0-9]{8}$ ]]; then
    TARGET_DATE="$ARG1"
else
    echo "Usage: $0 [YYYYMMDD|YYYYQX]"
    echo "Examples:"
    echo "  $0             # decide target quarter by today's date"
    echo "  $0 20260304    # decide by a specific date"
    echo "  $0 2025Q4      # force target quarter directly"
    exit 1
fi

if [[ -n "$TARGET_DATE" ]]; then
    year="${TARGET_DATE:0:4}"
    month="${TARGET_DATE:4:2}"
    day="${TARGET_DATE:6:2}"
    month_num=$((10#$month))
    day_num=$((10#$day))

    if (( month_num == 2 || month_num == 3 )); then
        target_year=$((10#$year - 1))
        target_q=4
    elif (( month_num == 4 )) || (( month_num == 5 && day_num <= 15 )); then
        target_year=$((10#$year))
        target_q=1
    elif (( month_num == 7 )) || (( month_num == 8 && day_num <= 15 )); then
        target_year=$((10#$year))
        target_q=2
    elif (( month_num == 10 )) || (( month_num == 11 && day_num <= 15 )); then
        target_year=$((10#$year))
        target_q=3
    else
        echo "========================================" | tee -a "$LOG_FILE"
        echo "XBRL Window Update Started" | tee -a "$LOG_FILE"
        echo "Date: $(date)" | tee -a "$LOG_FILE"
        echo "Input Date: $TARGET_DATE" | tee -a "$LOG_FILE"
        echo "Outside XBRL fetch windows. Skip." | tee -a "$LOG_FILE"
        echo "Windows:" | tee -a "$LOG_FILE"
        echo "  Q4 (prev year): 02/01~03/31" | tee -a "$LOG_FILE"
        echo "  Q1 (same year): 04/01~05/15" | tee -a "$LOG_FILE"
        echo "  Q2 (same year): 07/01~08/15" | tee -a "$LOG_FILE"
        echo "  Q3 (same year): 10/01~11/15" | tee -a "$LOG_FILE"
        echo "========================================" | tee -a "$LOG_FILE"
        exit 0
    fi

    TARGET_QUARTER="${target_year}Q${target_q}"
fi

if [[ ! "$TARGET_QUARTER" =~ ^([0-9]{4})Q([1-4])$ ]]; then
    echo "Error: invalid target quarter '$TARGET_QUARTER'"
    exit 1
fi

REPORT_YEAR="${BASH_REMATCH[1]}"
REPORT_QUARTER="${BASH_REMATCH[2]}"

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Window Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
if [[ -n "$TARGET_DATE" ]]; then
    echo "Input Date: $TARGET_DATE" | tee -a "$LOG_FILE"
fi
echo "Target Quarter: $TARGET_QUARTER" | tee -a "$LOG_FILE"
echo "FORCE_REPROCESS: ${FORCE_REPROCESS:-0}" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

echo "[1/1] Running XBRL fetch for $TARGET_QUARTER..." | tee -a "$LOG_FILE"
if docker compose run --rm \
    -e FORCE_REPROCESS=${FORCE_REPROCESS:-0} \
    scraper-quarterly \
    python3 scraper/quarterly/fetch_xbrl.py --year "$REPORT_YEAR" --quarter "$REPORT_QUARTER" 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ XBRL fetch completed" | tee -a "$LOG_FILE"
else
    echo "✗ XBRL fetch failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Window Update Completed" | tee -a "$LOG_FILE"
echo "Target Quarter: $TARGET_QUARTER" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "xbrl_update_*.log" -mtime +180 -delete
