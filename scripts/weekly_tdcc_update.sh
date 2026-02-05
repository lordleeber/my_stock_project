#!/bin/bash

# 每週 TDCC 集保資料更新腳本
# 執行順序: 查詢最新日期 -> scraper-weekly -> processor -> importer

set -e  # 遇到錯誤立即停止

# 設定工作目錄
cd "$(dirname "$0")/.."

# 設定日誌目錄
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/weekly_tdcc_update_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Weekly TDCC Data Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 1. 查詢 TDCC 可用的最新日期
echo "[1/4] Querying latest TDCC date..." | tee -a "$LOG_FILE"
TDCC_DATE=$(docker compose run --rm scraper-daily python -c "
from fetch_tdcc_history import TDCCScraper
scraper = TDCCScraper()
if scraper.initialize():
    print(scraper.available_dates[0])
" 2>/dev/null | tail -1)

if [ -z "$TDCC_DATE" ]; then
    echo "✗ Failed to get TDCC date" | tee -a "$LOG_FILE"
    exit 1
fi
echo "Latest TDCC date: $TDCC_DATE" | tee -a "$LOG_FILE"
export TDCC_DATE

# 2. Scraper (TDCC)
echo "[2/4] Running scraper-weekly for $TDCC_DATE..." | tee -a "$LOG_FILE"
docker compose run --rm -e TDCC_DATE=$TDCC_DATE scraper-weekly 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Scraper completed" | tee -a "$LOG_FILE"
else
    echo "✗ Scraper failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 3. Processor (shareholding)
echo "[3/4] Running processor for shareholding..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$TDCC_DATE -e END_DATE=$TDCC_DATE processor python convert_shareholding.py 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 4. Importer (shareholding_div only)
echo "[4/4] Running importer for shareholding_div..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$TDCC_DATE -e END_DATE=$TDCC_DATE -e IMPORT_CATEGORY=shareholding_div importer 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "Weekly TDCC Data Update Completed" | tee -a "$LOG_FILE"
echo "TDCC Date: $TDCC_DATE" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 保留最近 30 天的日誌
find "$LOG_DIR" -name "weekly_tdcc_update_*.log" -mtime +30 -delete
