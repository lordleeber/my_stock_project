#!/bin/bash

# 每週自動更新腳本
# 執行順序: scraper-weekly -> processor(convert_weekly) -> importer(shareholding)
#           -> processor(convert_dividend) -> importer(dividend)
# 註: 除權息 raw 由每日 scraper-daily 持續更新，這裡只需 process + import。

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
EXEC_TS=$(date +%Y%m%d_%H%M%S)
# TARGET_DATE 尚未確定，先用暫存 log，確定後 rename
LOG_FILE="$LOG_DIR/weekly_update_PENDING_${EXEC_TS}.log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Weekly Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 1) Scraper weekly
echo "[1/5] Running scraper-weekly..." | tee -a "$LOG_FILE"
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

# TARGET_DATE 確定後，rename log 為正式格式
FINAL_LOG="$LOG_DIR/weekly_update_${TARGET_DATE}_${EXEC_TS}.log"
mv "$LOG_FILE" "$FINAL_LOG"
LOG_FILE="$FINAL_LOG"

echo "Target Date: $TARGET_DATE" | tee -a "$LOG_FILE"

# 3) Processor weekly
echo "[2/5] Running processor (convert_weekly.py)..." | tee -a "$LOG_FILE"
if docker compose run --rm -e START_DATE=$TARGET_DATE -e END_DATE=$TARGET_DATE processor python convert_weekly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 4) Importer weekly
echo "[3/5] Running importer for shareholding..." | tee -a "$LOG_FILE"
if docker compose run --rm -e START_DATE=$TARGET_DATE -e END_DATE=$TARGET_DATE importer python import_weekly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 5) Processor dividend（只重算當年度；raw 由每日 scrape 維持最新）
echo "[4/5] Running processor (convert_dividend.py)..." | tee -a "$LOG_FILE"
if docker compose run --rm processor python convert_dividend.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Dividend processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Dividend processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 6) Importer dividend（當年度 delete-before-insert，不 drop 整表）
echo "[5/5] Running importer (import_dividend.py)..." | tee -a "$LOG_FILE"
if docker compose run --rm importer python import_dividend.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Dividend importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Dividend importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "Weekly Update Completed" | tee -a "$LOG_FILE"
echo "Target Date: $TARGET_DATE" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "weekly_update_*.log" -mtime +90 -delete
