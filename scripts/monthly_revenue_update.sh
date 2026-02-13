#!/bin/bash

# 每月營收自動更新腳本
# 排程: 每月 11 號執行，抓取上個月的營收
# 執行順序: scraper-monthly -> processor -> importer

set -e

# 設定工作目錄
cd "$(dirname "$0")/.."

# 設定日誌目錄
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/monthly_revenue_update_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Monthly Revenue Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 計算上個月的年份和月份
CURRENT_MONTH=$(date +%m)
CURRENT_YEAR=$(date +%Y)

if [ "$CURRENT_MONTH" -eq 1 ]; then
    REVENUE_YEAR=$((CURRENT_YEAR - 1))
    REVENUE_MONTH=12
else
    REVENUE_YEAR=$CURRENT_YEAR
    REVENUE_MONTH=$((10#$CURRENT_MONTH - 1))
fi

# 用於 processor/importer 的日期格式 (YYYYMMDD，日期固定為 01)
REVENUE_DATE=$(printf "%d%02d01" "$REVENUE_YEAR" "$REVENUE_MONTH")

echo "Target: ${REVENUE_YEAR}/${REVENUE_MONTH}" | tee -a "$LOG_FILE"

# 1. Scraper
echo "[1/3] Running scraper-monthly for ${REVENUE_YEAR}/${REVENUE_MONTH}..." | tee -a "$LOG_FILE"
REVENUE_YEAR=$REVENUE_YEAR REVENUE_MONTH=$REVENUE_MONTH docker compose run --rm scraper-monthly 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Scraper completed" | tee -a "$LOG_FILE"
else
    echo "✗ Scraper failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 2. Processor
echo "[2/3] Running processor for monthly revenue..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$REVENUE_DATE -e END_DATE=$REVENUE_DATE processor python convert_monthly.py 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 3. Importer
echo "[3/3] Running importer for monthly_revenue..." | tee -a "$LOG_FILE"
docker compose run --rm -e START_DATE=$REVENUE_DATE -e END_DATE=$REVENUE_DATE -e IMPORT_CATEGORY=monthly_revenue importer 2>&1 | tee -a "$LOG_FILE"
if [ $? -eq 0 ]; then
    echo "✓ Importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "Monthly Revenue Update Completed" | tee -a "$LOG_FILE"
echo "Revenue: ${REVENUE_YEAR}/${REVENUE_MONTH}" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 保留最近 90 天的日誌
find "$LOG_DIR" -name "monthly_revenue_update_*.log" -mtime +90 -delete
