#!/bin/bash

# ==============================================================================
# Daily Calculator - 負責資料匯入後的衍生數據計算與分析
# ==============================================================================

# 取得日期參數 (YYYYMMDD)，若無則預設為空 (依據各腳本內部邏輯處理)
TARGET_DATE=$1

echo "=============================================================================="
echo "🚀 Starting Daily Calculator Tasks..."
echo "Date: ${TARGET_DATE:-Full History / Latest}"
echo "=============================================================================="

# 1. 計算技術指標 (MA, RSI, MACD, Bollinger Bands)
echo ">>> [1/2] Calculating Technical Indicators..."
if [ -n "$TARGET_DATE" ]; then
    START_DATE=$TARGET_DATE END_DATE=$TARGET_DATE docker compose run --rm calculator python calculate_daily.py
else
    docker compose run --rm calculator python calculate_daily.py
fi

# 2. 計算前瞻估值分析 (TTM EPS, PE Forward, ROE, Upside Potential)
echo -e "
>>> [2/2] Calculating Forward-looking Valuations (PE/ROE)..."
docker compose run --rm calculator python calculate_valuation.py

echo -e "
=============================================================================="
echo "✅ All Daily Calculations Finished Successfully."
echo "=============================================================================="
