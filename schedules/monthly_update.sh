#!/bin/bash

# 每月自動更新腳本
# 排程: 每月 11 號執行，抓取上個月的營收
# 執行順序: scraper-monthly -> generate active stocks -> processor -> importer -> publish active stocks
# (generate + publish active_stocks 只在 15 號跑)

set -euo pipefail

# 設定工作目錄
cd "$(dirname "$0")/.."

# 設定日誌目錄
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
EXEC_TS=$(date +%Y%m%d_%H%M%S)

# 計算上個月的年份和月份（log 命名需要，先算）
TODAY_DAY=$(date +%d)
CURRENT_MONTH=$(date +%m)
CURRENT_YEAR=$(date +%Y)

if [ "$CURRENT_MONTH" -eq 1 ]; then
    REVENUE_YEAR=$((CURRENT_YEAR - 1))
    REVENUE_MONTH=12
else
    REVENUE_YEAR=$CURRENT_YEAR
    REVENUE_MONTH=$((10#$CURRENT_MONTH - 1))
fi

TARGET_MONTH=$(printf "%d%02d" "$REVENUE_YEAR" "$REVENUE_MONTH")

# 用於 processor/importer 的日期格式 (YYYYMMDD，日期固定為 01)
REVENUE_DATE=$(printf "%d%02d01" "$REVENUE_YEAR" "$REVENUE_MONTH")

LOG_FILE="$LOG_DIR/monthly_update_${TARGET_MONTH}_${EXEC_TS}.log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Monthly Revenue Update Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 僅在每月 1~15 日執行（公告期間）
if [ "$TODAY_DAY" -lt 1 ] || [ "$TODAY_DAY" -gt 15 ]; then
    echo "Outside publish window (day=$TODAY_DAY). Skip monthly update." | tee -a "$LOG_FILE"
    exit 0
fi

echo "Target: ${REVENUE_YEAR}/${REVENUE_MONTH}" | tee -a "$LOG_FILE"

# 1. Scraper
echo "[1/5] Running scraper-monthly for ${REVENUE_YEAR}/${REVENUE_MONTH}..." | tee -a "$LOG_FILE"
if REVENUE_YEAR=$REVENUE_YEAR REVENUE_MONTH=$REVENUE_MONTH docker compose run --rm scraper-monthly 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Scraper completed" | tee -a "$LOG_FILE"
else
    echo "✗ Scraper failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 2. Generate active_stocks.txt (only on day 15)
if [ "$TODAY_DAY" -eq 15 ]; then
    echo "[2/5] Generating active_stocks.txt..." | tee -a "$LOG_FILE"
    if python3 scraper/monthly/generate_active_stocks.py --date "$REVENUE_DATE" --output active_stocks.txt 2>&1 | tee -a "$LOG_FILE"; then
        echo "✓ Active stocks generated" | tee -a "$LOG_FILE"
    else
        echo "✗ Failed to generate active_stocks.txt" | tee -a "$LOG_FILE"
        exit 1
    fi
else
    echo "[2/5] Skipping active_stocks.txt generation (only runs on day 15)." | tee -a "$LOG_FILE"
fi

# 3. Processor
echo "[3/5] Running processor for monthly revenue..." | tee -a "$LOG_FILE"
if docker compose run --rm -e START_DATE=$REVENUE_DATE -e END_DATE=$REVENUE_DATE processor python convert_monthly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Processor completed" | tee -a "$LOG_FILE"
else
    echo "✗ Processor failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 4. Importer (force reimport to refresh cumulative monthly publication progress)
echo "[4/5] Running importer for monthly_revenue..." | tee -a "$LOG_FILE"
if docker compose run --rm -e FORCE_REIMPORT=1 -e START_DATE=$REVENUE_DATE -e END_DATE=$REVENUE_DATE importer python import_monthly.py 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ Importer completed" | tee -a "$LOG_FILE"
else
    echo "✗ Importer failed" | tee -a "$LOG_FILE"
    exit 1
fi

# 5. Publish active_stocks to My Stock Server (only on day 15, after regeneration).
#    Placed after the importer so a push failure never blocks the revenue import;
#    a failure here trips set -e -> non-zero exit -> OnFailure phone push. API host
#    overridable via STOCK_LIST_API_BASE (default http://100.101.183.80:8053).
if [ "$TODAY_DAY" -eq 15 ]; then
    echo "[5/5] Publishing active_stocks.txt to My Stock Server..." | tee -a "$LOG_FILE"
    if venv/bin/python3 scripts/publish_active_stocks.py 2>&1 | tee -a "$LOG_FILE"; then
        echo "✓ Active stocks published" | tee -a "$LOG_FILE"
    else
        echo "✗ Failed to publish active_stocks" | tee -a "$LOG_FILE"
        exit 1
    fi
else
    echo "[5/5] Skipping active_stocks publish (only runs on day 15)." | tee -a "$LOG_FILE"
fi

echo "========================================" | tee -a "$LOG_FILE"
echo "Monthly Revenue Update Completed" | tee -a "$LOG_FILE"
echo "Revenue: ${REVENUE_YEAR}/${REVENUE_MONTH}" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 保留最近 90 天的日誌
find "$LOG_DIR" -name "monthly_update_*.log" -mtime +30 -delete
