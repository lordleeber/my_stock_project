#!/bin/bash
# 季報 XBRL 每日 scrape（公告期內持續累積 raw 資料；不跑 process / import）
#
# 公告時程：
#   Q4 (前一年):   02/01 ~ 03/31
#   Q1 (同年):     04/01 ~ 05/15
#   Q2 (同年):     07/01 ~ 08/15
#   Q3 (同年):     10/01 ~ 11/15
#   其他日期：     skip
#
# DB 入庫由 `xbrl_run_pipeline.sh` 手動觸發（公告期末 / 補資料時）。

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
EXEC_TS=$(date +%Y%m%d_%H%M%S)

ARG1="${1:-}"
TARGET_DATE=""
TARGET_QUARTER=""
SKIP_MODE=0

if [[ -z "$ARG1" ]]; then
    TARGET_DATE="$(date +%Y%m%d)"
elif [[ "$ARG1" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    TARGET_QUARTER="$ARG1"
elif [[ "$ARG1" =~ ^[0-9]{8}$ ]]; then
    TARGET_DATE="$ARG1"
else
    echo "Usage: $0 [YYYYMMDD|YYYYQX]"
    exit 1
fi

if [[ -n "$TARGET_DATE" ]]; then
    year="${TARGET_DATE:0:4}"
    month="${TARGET_DATE:4:2}"
    day="${TARGET_DATE:6:2}"
    month_num=$((10#$month))
    day_num=$((10#$day))

    if (( month_num == 2 || month_num == 3 )); then
        TARGET_QUARTER="$((10#$year - 1))Q4"
    elif (( month_num == 4 )) || (( month_num == 5 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q1"
    elif (( month_num == 7 )) || (( month_num == 8 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q2"
    elif (( month_num == 10 )) || (( month_num == 11 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q3"
    else
        SKIP_MODE=1
    fi
fi

if [[ "$SKIP_MODE" -eq 1 ]]; then
    LOG_FILE="$LOG_DIR/xbrl_scrape_skip_${EXEC_TS}.log"
else
    if [[ ! "$TARGET_QUARTER" =~ ^([0-9]{4})Q([1-4])$ ]]; then
        echo "Error: invalid target quarter '$TARGET_QUARTER'"
        exit 1
    fi
    LOG_FILE="$LOG_DIR/xbrl_scrape_${TARGET_QUARTER}_${EXEC_TS}.log"
fi

if [[ "$SKIP_MODE" -eq 1 ]]; then
    {
        echo "========================================"
        echo "XBRL Scrape Skipped"
        echo "Date: $(date)"
        echo "Input Date: $TARGET_DATE"
        echo "Outside XBRL fetch windows."
        echo "========================================"
    } | tee -a "$LOG_FILE"
    exit 0
fi

REPORT_YEAR="${BASH_REMATCH[1]}"
REPORT_QUARTER="${BASH_REMATCH[2]}"

{
    echo "========================================"
    echo "XBRL Scrape Started"
    echo "Date: $(date)"
    [[ -n "$TARGET_DATE" ]] && echo "Input Date: $TARGET_DATE"
    echo "Target Quarter: $TARGET_QUARTER"
    echo "FORCE_REPROCESS: ${FORCE_REPROCESS:-0}"
    echo "========================================"
} | tee -a "$LOG_FILE"

if docker compose run --rm \
    -e FORCE_REPROCESS=${FORCE_REPROCESS:-0} \
    scraper-quarterly \
    python3 scraper/quarterly/fetch_xbrl.py --year "$REPORT_YEAR" --quarter "$REPORT_QUARTER" 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ XBRL scrape done" | tee -a "$LOG_FILE"
else
    echo "✗ XBRL scrape failed" | tee -a "$LOG_FILE"
    exit 1
fi

{
    echo "========================================"
    echo "XBRL Scrape Completed"
    echo "Target Quarter: $TARGET_QUARTER"
    echo "Date: $(date)"
    echo "========================================"
} | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "xbrl_scrape_*.log" -mtime +30 -delete
