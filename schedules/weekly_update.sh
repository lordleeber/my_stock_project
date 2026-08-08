#!/bin/bash

# 每週自動更新腳本
#
# 兩條互相獨立的分支：
#   A. shareholding: scraper-weekly -> processor(convert_weekly) -> importer(import_weekly)
#   B. dividend:     processor(convert_dividend) -> importer(import_dividend)
#
# B 完全不吃 TDCC——除權息 raw 由每日 scraper-daily 持續累積，這裡只需 process +
# import。所以 A 失敗（例如 TDCC 延遲發布、農曆年沒有快照，觸發新鮮度 gate）時
# **不能**把 B 一起拖下水：weekly 沒有 retry timer，一次連坐就是除權息整整一週
# 不更新。這裡改成兩條分支各自記錄成敗、B 無論如何都跑，最後只要有任何一條失敗
# 就以非零退出，systemd 的 OnFailure 照樣推播。

set -euo pipefail

cd "$(dirname "$0")/.."

./schedules/ensure_error_logs.sh

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
EXEC_TS=$(date +%Y%m%d_%H%M%S)
# TARGET_DATE 尚未確定，先用暫存 log，確定後 rename
LOG_FILE="$LOG_DIR/weekly_update_PENDING_${EXEC_TS}.log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Weekly Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

SHAREHOLDING_OK=1
DIVIDEND_OK=1
TARGET_DATE=""

# ---- 分支 A: shareholding ----------------------------------------------------

# A1) Scraper weekly
echo "[1/5] Running scraper-weekly..." | tee -a "$LOG_FILE"
if docker compose run --rm scraper-weekly 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Scraper completed" | tee -a "$LOG_FILE"
else
    echo "✗ Scraper failed" | tee -a "$LOG_FILE"
    SHAREHOLDING_OK=0
fi

# A2) Detect latest TDCC date from raw shareholding files
if [ "$SHAREHOLDING_OK" -eq 1 ]; then
    LATEST_TDCC_FILE=$(find data/raw/shareholding -type f -name 'TDCC_OD_1-5_*.csv' | sort | tail -n 1)
    if [ -z "${LATEST_TDCC_FILE:-}" ]; then
        echo "✗ No TDCC file found under data/raw/shareholding" | tee -a "$LOG_FILE"
        SHAREHOLDING_OK=0
    else
        TARGET_DATE=$(basename "$LATEST_TDCC_FILE" | sed -E 's/^TDCC_OD_1-5_([0-9]{8})\.csv$/\1/')
        if ! [[ "$TARGET_DATE" =~ ^[0-9]{8}$ ]]; then
            echo "✗ Failed to parse target date from file: $LATEST_TDCC_FILE" | tee -a "$LOG_FILE"
            TARGET_DATE=""
            SHAREHOLDING_OK=0
        fi
    fi
fi

# TARGET_DATE 確定後，rename log 為正式格式（A 失敗時標成 UNKNOWN，別留 PENDING）
FINAL_LOG="$LOG_DIR/weekly_update_${TARGET_DATE:-UNKNOWN}_${EXEC_TS}.log"
mv "$LOG_FILE" "$FINAL_LOG"
LOG_FILE="$FINAL_LOG"

echo "Target Date: ${TARGET_DATE:-<unresolved>}" | tee -a "$LOG_FILE"

# A3) Processor weekly
if [ "$SHAREHOLDING_OK" -eq 1 ]; then
    echo "[2/5] Running processor (convert_weekly.py)..." | tee -a "$LOG_FILE"
    if docker compose run --rm -e START_DATE=$TARGET_DATE -e END_DATE=$TARGET_DATE processor python convert_weekly.py 2>&1 | tee -a "$LOG_FILE"; then
        echo "✓ Processor completed" | tee -a "$LOG_FILE"
    else
        echo "✗ Processor failed" | tee -a "$LOG_FILE"
        SHAREHOLDING_OK=0
    fi
fi

# A4) Importer weekly
if [ "$SHAREHOLDING_OK" -eq 1 ]; then
    echo "[3/5] Running importer for shareholding..." | tee -a "$LOG_FILE"
    if docker compose run --rm -e START_DATE=$TARGET_DATE -e END_DATE=$TARGET_DATE importer python import_weekly.py 2>&1 | tee -a "$LOG_FILE"; then
        echo "✓ Importer completed" | tee -a "$LOG_FILE"
    else
        echo "✗ Importer failed" | tee -a "$LOG_FILE"
        SHAREHOLDING_OK=0
    fi
fi

if [ "$SHAREHOLDING_OK" -eq 0 ]; then
    echo "⚠ Shareholding branch failed — 繼續跑 dividend（兩者無相依）" | tee -a "$LOG_FILE"
fi

# ---- 分支 B: dividend（與 TDCC 無關，A 失敗也照跑）---------------------------

# B1) Processor dividend（只重算當年度；raw 由每日 scrape 維持最新）
echo "[4/5] Running processor (convert_dividend.py)..." | tee -a "$LOG_FILE"
if docker compose run --rm processor python convert_dividend.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Dividend processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Dividend processor failed" | tee -a "$LOG_FILE"
    DIVIDEND_OK=0
fi

# B2) Importer dividend（當年度 delete-before-insert，不 drop 整表）
if [ "$DIVIDEND_OK" -eq 1 ]; then
    echo "[5/5] Running importer (import_dividend.py)..." | tee -a "$LOG_FILE"
    if docker compose run --rm importer python import_dividend.py 2>&1 | tee -a "$LOG_FILE"; then
        echo "✓ Dividend importer completed" | tee -a "$LOG_FILE"
    else
        echo "✗ Dividend importer failed" | tee -a "$LOG_FILE"
        DIVIDEND_OK=0
    fi
fi

echo "========================================" | tee -a "$LOG_FILE"
if [ "$SHAREHOLDING_OK" -eq 1 ] && [ "$DIVIDEND_OK" -eq 1 ]; then
    echo "Weekly Update Completed" | tee -a "$LOG_FILE"
    EXIT_CODE=0
else
    echo "Weekly Update FAILED" | tee -a "$LOG_FILE"
    [ "$SHAREHOLDING_OK" -eq 1 ] || echo "  - shareholding branch failed" | tee -a "$LOG_FILE"
    [ "$DIVIDEND_OK" -eq 1 ] || echo "  - dividend branch failed" | tee -a "$LOG_FILE"
    EXIT_CODE=1
fi
echo "Target Date: ${TARGET_DATE:-<unresolved>}" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "weekly_update_*.log" -mtime +90 -delete

exit "$EXIT_CODE"
