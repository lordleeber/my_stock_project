#!/bin/bash

# 每週自動更新腳本
# 執行順序: scraper-weekly -> processor(convert_weekly) -> importer(shareholding)

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_update_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Weekly Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 1) Scraper weekly
echo "[1/3] Running scraper-weekly..." | tee -a "$LOG_FILE"
if docker compose run --rm scraper-weekly 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Scraper completed" | tee -a "$LOG_FILE"
else
    echo "✗ Scraper failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 2) Detect latest TDCC date from raw shareholding files
LATEST_TDCC_FILE=$(find data/raw/shareholding -type f -name 'TDCC_OD_1-5_*.csv' | sort | tail -n 1)
if [ -z "${LATEST_TDCC_FILE:-}" ]; then
    echo "✗ No TDCC file found under data/raw/shareholding" | tee -a "$LOG_FILE"
    exit 1
fi

TARGET_DATE=$(basename "$LATEST_TDCC_FILE" | sed -E 's/^TDCC_OD_1-5_([0-9]{8})\.csv$/\1/')
if ! [[ "$TARGET_DATE" =~ ^[0-9]{8}$ ]]; then
    echo "✗ Failed to parse target date from file: $LATEST_TDCC_FILE" | tee -a "$LOG_FILE"
    exit 1
fi

echo "Target Date: $TARGET_DATE" | tee -a "$LOG_FILE"

# 3) Processor weekly
echo "[2/3] Running processor (convert_weekly.py)..." | tee -a "$LOG_FILE"
if docker compose run --rm -e START_DATE=$TARGET_DATE -e END_DATE=$TARGET_DATE processor python convert_weekly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 4) Importer weekly
echo "[3/3] Running importer for shareholding..." | tee -a "$LOG_FILE"
if docker compose run --rm -e START_DATE=$TARGET_DATE -e END_DATE=$TARGET_DATE importer python import_weekly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "Weekly Update Completed" | tee -a "$LOG_FILE"
echo "Target Date: $TARGET_DATE" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "weekly_update_*.log" -mtime +90 -delete
