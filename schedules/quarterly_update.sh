#!/bin/bash

# 每季自動更新腳本
# 執行順序: scraper-quarterly -> processor(convert_quarterly) -> importer(quarterly categories)

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
EXEC_TS=$(date +%Y%m%d_%H%M%S)

# Optional arg: YYYYQX
INPUT_QUARTER="${1:-}"

if [ -n "$INPUT_QUARTER" ]; then
    if [[ "$INPUT_QUARTER" =~ ^([0-9]{4})Q([1-4])$ ]]; then
        REPORT_YEAR="${BASH_REMATCH[1]}"
        REPORT_QUARTER="${BASH_REMATCH[2]}"
    else
        echo "Error: invalid quarter '$INPUT_QUARTER'. Expected YYYYQX (e.g., 2025Q3)."
        exit 1
    fi
else
    # Default to previous quarter
    YEAR_NOW=$(date +%Y)
    MONTH_NOW=$(date +%m)
    CUR_Q=$(( (10#$MONTH_NOW - 1) / 3 + 1 ))
    if [ "$CUR_Q" -eq 1 ]; then
        REPORT_YEAR=$((YEAR_NOW - 1))
        REPORT_QUARTER=4
    else
        REPORT_YEAR=$YEAR_NOW
        REPORT_QUARTER=$((CUR_Q - 1))
    fi
fi

TARGET_QUARTER="${REPORT_YEAR}Q${REPORT_QUARTER}"
LOG_FILE="$LOG_DIR/quarterly_update_${TARGET_QUARTER}_${EXEC_TS}.log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Quarterly Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Target Quarter: $TARGET_QUARTER" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 1) Scraper quarterly
echo "[1/3] Running scraper-quarterly for $TARGET_QUARTER..." | tee -a "$LOG_FILE"
if docker compose run --rm -e REPORT_YEAR=$REPORT_YEAR -e REPORT_QUARTER=$REPORT_QUARTER scraper-quarterly 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Scraper completed" | tee -a "$LOG_FILE"
else
    echo "✗ Scraper failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 2) Processor quarterly
echo "[2/3] Running processor (convert_quarterly.py)..." | tee -a "$LOG_FILE"
if docker compose run --rm -e QUARTERLY_TASK=all -e START_DATE=$TARGET_QUARTER -e END_DATE=$TARGET_QUARTER processor python convert_quarterly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 3) Importer quarterly
echo "[3/3] Running importer (import_quarterly.py)..." | tee -a "$LOG_FILE"
if docker compose run --rm -e START_DATE=$TARGET_QUARTER -e END_DATE=$TARGET_QUARTER importer python import_quarterly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "Quarterly Update Completed" | tee -a "$LOG_FILE"
echo "Target Quarter: $TARGET_QUARTER" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "quarterly_update_*.log" -mtime +180 -delete
