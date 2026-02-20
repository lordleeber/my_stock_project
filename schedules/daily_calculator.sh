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
echo ">>> [1/5] Calculating Technical Indicators..."
if [ -n "$TARGET_DATE" ]; then
    START_DATE=$TARGET_DATE END_DATE=$TARGET_DATE docker compose run --rm calculator python calculate_daily.py
else
    docker compose run --rm calculator python calculate_daily.py
fi

# 2. 計算投信持股統計 (trust_holding)
echo -e "
>>> [2/5] Calculating Trust Holding..."
docker compose run --rm calculator python calculate_trust_holding.py

# 3. 計算自營商持股統計 (dealer_holding)
echo -e "
>>> [3/5] Calculating Dealer Holding..."
docker compose run --rm calculator python calculate_dealer_holding.py

# 4. 計算大戶/散戶集中度衍生指標
echo -e "
>>> [4/5] Calculating Shareholding Concentration..."
docker compose run --rm calculator python calculate_shareholding_concentration.py

# 5. 計算前瞻估值分析 (TTM EPS, PE Forward, ROE, Upside Potential)
echo -e "
>>> [5/5] Calculating Forward-looking Valuations (PE/ROE)..."
docker compose run --rm calculator python calculate_valuation.py

echo -e "
=============================================================================="
echo "✅ All Daily Calculations Finished Successfully."
echo "=============================================================================="
