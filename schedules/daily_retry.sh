#!/bin/bash

# 每日資料補跑腳本
# 檢查前一天的 daily_update 是否成功，失敗則重新執行
# 由 launchd 在 02:00 及 04:00 各觸發一次

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

# 取得目標日期（昨天，macOS 語法）
TARGET_DATE="${1:-$(date -v-1d +%Y%m%d)}"
LOG_FILE="$LOG_DIR/daily_retry_${TARGET_DATE}_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "Daily Retry Check Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Target Date: $TARGET_DATE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 找出所有處理過該 target date 的 log（檔名前綴即為 target date）
LOG_PATTERN="$LOG_DIR/daily_update_${TARGET_DATE}_*.log"

# 非交易日 → skip
if ls $LOG_PATTERN 2>/dev/null | xargs grep -l "No valid trading days" 2>/dev/null \
   | xargs grep -l "Target Date: $TARGET_DATE" 2>/dev/null | grep -q .; then
    echo "Target date $TARGET_DATE is a non-trading day. Skipping." | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    exit 0
fi

# 是否曾有「daily_update 走完」的紀錄
LOG_COMPLETED=0
if ls $LOG_PATTERN 2>/dev/null | xargs grep -l "Daily Stock Data Update Completed" 2>/dev/null \
   | xargs grep -l "Target Date: $TARGET_DATE" 2>/dev/null | grep -q .; then
    LOG_COMPLETED=1
fi

# 即使 log 說完成，仍檢查 raw 完整性（防止 scraper 拿到 empty 但靜默通過的情況）
YEAR=${TARGET_DATE:0:4}
RAW_DIR="./data/raw"
DATASETS_BOTH=(daily_quotes institutional_summary institutional_investors \
               foreign_holding margin_trading margin_sbl pe_ratio)
DATASETS_OTC_ONLY=(market_indices)
RAW_MISSING=0
for ds in "${DATASETS_BOTH[@]}"; do
    for mkt in sii otc; do
        f="$RAW_DIR/$ds/$YEAR/$TARGET_DATE/$mkt.csv"
        if [ ! -s "$f" ]; then
            echo "[RAW-MISSING] $f" | tee -a "$LOG_FILE"
            RAW_MISSING=1
        fi
    done
done
for ds in "${DATASETS_OTC_ONLY[@]}"; do
    f="$RAW_DIR/$ds/$YEAR/$TARGET_DATE/otc.csv"
    if [ ! -s "$f" ]; then
        echo "[RAW-MISSING] $f" | tee -a "$LOG_FILE"
        RAW_MISSING=1
    fi
done

# 第三層：檢查 DB 該日是否每個 (table, market) 都有資料
# 用來防止「raw 完整、processed/all.csv stale、DB 只進部分 market」這類隱性缺漏
# market_indices 已知從 2026-02 後沒進 DB（另一個獨立 bug），暫不納入檢查
TARGET_ISO="${TARGET_DATE:0:4}-${TARGET_DATE:4:2}-${TARGET_DATE:6:2}"
DB_MISSING_LIST=$(docker compose exec -T db psql -U user -d stock_db -tAc "
SELECT tbl || '/' || mkt FROM (
    SELECT 'daily_quotes' AS tbl, 'sii' AS mkt, (SELECT count(*) FROM daily_quotes WHERE date='$TARGET_ISO' AND lower(market)='sii') AS n
    UNION ALL SELECT 'daily_quotes','otc', (SELECT count(*) FROM daily_quotes WHERE date='$TARGET_ISO' AND lower(market)='otc')
    UNION ALL SELECT 'institutional_investors','sii', (SELECT count(*) FROM institutional_investors WHERE date='$TARGET_ISO' AND lower(market)='sii')
    UNION ALL SELECT 'institutional_investors','otc', (SELECT count(*) FROM institutional_investors WHERE date='$TARGET_ISO' AND lower(market)='otc')
    UNION ALL SELECT 'foreign_holding','sii', (SELECT count(*) FROM foreign_holding WHERE date='$TARGET_ISO' AND lower(market)='sii')
    UNION ALL SELECT 'foreign_holding','otc', (SELECT count(*) FROM foreign_holding WHERE date='$TARGET_ISO' AND lower(market)='otc')
    UNION ALL SELECT 'margin_trading','sii', (SELECT count(*) FROM margin_trading WHERE date='$TARGET_ISO' AND lower(market)='sii')
    UNION ALL SELECT 'margin_trading','otc', (SELECT count(*) FROM margin_trading WHERE date='$TARGET_ISO' AND lower(market)='otc')
    UNION ALL SELECT 'margin_sbl','sii', (SELECT count(*) FROM margin_sbl WHERE date='$TARGET_ISO' AND lower(market)='sii')
    UNION ALL SELECT 'margin_sbl','otc', (SELECT count(*) FROM margin_sbl WHERE date='$TARGET_ISO' AND lower(market)='otc')
    UNION ALL SELECT 'pe_ratio','sii', (SELECT count(*) FROM pe_ratio WHERE date='$TARGET_ISO' AND lower(market)='sii')
    UNION ALL SELECT 'pe_ratio','otc', (SELECT count(*) FROM pe_ratio WHERE date='$TARGET_ISO' AND lower(market)='otc')
    UNION ALL SELECT 'institutional_summary','sii', (SELECT count(*) FROM institutional_summary WHERE date='$TARGET_ISO' AND lower(market)='sii')
    UNION ALL SELECT 'institutional_summary','otc', (SELECT count(*) FROM institutional_summary WHERE date='$TARGET_ISO' AND lower(market)='otc')
    UNION ALL SELECT 'margin_summary','sii', (SELECT count(*) FROM margin_summary WHERE date='$TARGET_ISO' AND lower(market)='sii')
    UNION ALL SELECT 'margin_summary','otc', (SELECT count(*) FROM margin_summary WHERE date='$TARGET_ISO' AND lower(market)='otc')
) t WHERE n = 0;
" 2>/dev/null || true)

DB_MISSING=0
if [ -n "$DB_MISSING_LIST" ]; then
    echo "[DB-MISSING]" | tee -a "$LOG_FILE"
    echo "$DB_MISSING_LIST" | sed 's/^/  - /' | tee -a "$LOG_FILE"
    DB_MISSING=1
fi

# 三層全綠 → skip
if [ "$LOG_COMPLETED" = "1" ] && [ "$RAW_MISSING" = "0" ] && [ "$DB_MISSING" = "0" ]; then
    echo "Target date $TARGET_DATE: log/raw/db all intact. Skipping." | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    exit 0
fi

# raw 缺：scraper 階段會重抓 → 不需 force flags
if [ "$RAW_MISSING" = "1" ]; then
    echo "Raw incomplete. Will re-run full pipeline (scraper will fill gaps)." | tee -a "$LOG_FILE"
fi

# raw 完整但 DB 缺：processed/all.csv 可能 stale，importer 也會看 already-in-DB 而 skip
# 必須 FORCE_REPROCESS + FORCE_REIMPORT 才能把 processed 重建並覆寫 DB
if [ "$RAW_MISSING" = "0" ] && [ "$DB_MISSING" = "1" ]; then
    echo "Raw OK but DB incomplete. Forcing reprocess + reimport." | tee -a "$LOG_FILE"
    export FORCE_REPROCESS=1
    export FORCE_REIMPORT=1
fi

if [ "$LOG_COMPLETED" = "1" ] && [ "$RAW_MISSING" = "1" ]; then
    echo "Log shows completed but raw is incomplete. Forcing retry." | tee -a "$LOG_FILE"
fi

# 需要 retry
echo "Target date $TARGET_DATE did not complete successfully. Running retry..." | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

CALLED_BY_RETRY=1 ./schedules/daily_update.sh "$TARGET_DATE" 2>&1 | tee -a "$LOG_FILE"

echo "========================================" | tee -a "$LOG_FILE"
echo "Daily Retry Check Completed" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 保留最近 30 天的 retry log
find "$LOG_DIR" -name "daily_retry_*.log" -mtime +30 -delete
