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

# 檢查是否已成功完成
if ls $LOG_PATTERN 2>/dev/null | xargs grep -l "Daily Stock Data Update Completed" 2>/dev/null | grep -q .; then
    echo "Target date $TARGET_DATE already completed successfully. Skipping." | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    exit 0
fi

# 檢查是否為非交易日
if ls $LOG_PATTERN 2>/dev/null | xargs grep -l "No valid trading days" 2>/dev/null | grep -q .; then
    echo "Target date $TARGET_DATE is a non-trading day. Skipping." | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    exit 0
fi

# 需要 retry
echo "Target date $TARGET_DATE did not complete successfully. Running retry..." | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

./schedules/daily_update.sh "$TARGET_DATE" 2>&1 | tee -a "$LOG_FILE"

echo "========================================" | tee -a "$LOG_FILE"
echo "Daily Retry Check Completed" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

# 保留最近 30 天的 retry log
find "$LOG_DIR" -name "daily_retry_*.log" -mtime +30 -delete
