#!/bin/bash

# 每日股票數據更新腳本
# 執行順序: scraper -> processor -> data_quality_checker -> importer -> calculator

set -e  # 遇到錯誤立即停止
set -o pipefail  # 確保管道指令中任何一段失敗都會回傳錯誤碼

# 設定工作目錄
cd "$(dirname "$0")/.."

# 設定日期範圍（支援傳入日期參數，預設為今天）
TARGET_DATE=${1:-$(date +%Y%m%d)}
export START_DATE=$TARGET_DATE
export END_DATE=$TARGET_DATE

# 設定日誌目錄
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/daily_update_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Daily Stock Data Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Target Date: $TARGET_DATE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 1. Scraper
echo "[1/6] Running scraper..." | tee -a "$LOG_FILE"
docker compose run --rm scraper-daily 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Scraper completed" | tee -a "$LOG_FILE"
else
    echo "✗ Scraper failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 2. Processor (daily)
echo "[2/6] Running processor..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$START_DATE -e END_DATE=$END_DATE processor 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 3. Processor (institutional_summary)
echo "[3/6] Running institutional_summary processor..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$START_DATE -e END_DATE=$END_DATE processor python convert_institutional_summary.py 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Institutional summary processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Institutional summary processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 4. Data Quality Checker (runs after all processor steps)
echo "[4/6] Running data quality checker..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$START_DATE processor python data_quality_checker.py 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Data quality check passed" | tee -a "$LOG_FILE"
else
    echo "❌ Data quality check FAILED (see error_processor.md)" | tee -a "$LOG_FILE"
    echo "❌ Stopping update to prevent database contamination." | tee -a "$LOG_FILE"
    exit 1
fi

# 5. Importer
echo "[5/6] Running importer..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$START_DATE -e END_DATE=$END_DATE importer 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 6. Calculator
echo "[6/6] Running calculator..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$START_DATE -e END_DATE=$END_DATE calculator 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Calculator completed" | tee -a "$LOG_FILE"
else
    echo "✗ Calculator failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "Daily Stock Data Update Completed" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 保留最近 30 天的日誌
find "$LOG_DIR" -name "daily_update_*.log" -mtime +30 -delete
