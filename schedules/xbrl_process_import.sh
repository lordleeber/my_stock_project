#!/bin/bash
# 季報 XBRL：process + import（不含 scrape）
# 寫入 DB：quarterly_reports_xbrl / balance_sheet_xbrl / income_statement_xbrl / cash_flow_xbrl (+ xbrl_codebook)
#
# 前提：raw XBRL 已存在（由 xbrl_scrape_daily.sh 累積，或手動跑 fetch_xbrl.py）。
# 一般於公告期末或補資料時手動觸發。

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
EXEC_TS=$(date +%Y%m%d_%H%M%S)

ARG1="${1:-}"
TARGET_DATE=""
TARGET_QUARTER=""

if [[ -z "$ARG1" ]]; then
    TARGET_DATE="$(date +%Y%m%d)"
elif [[ "$ARG1" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    TARGET_QUARTER="$ARG1"
elif [[ "$ARG1" =~ ^[0-9]{8}$ ]]; then
    TARGET_DATE="$ARG1"
else
    echo "Usage: $0 [YYYYMMDD|YYYYQX]"
    echo "Examples:"
    echo "  $0             # 由今天日期決定季別（限公告窗口內）"
    echo "  $0 20260304    # 由指定日期決定季別"
    echo "  $0 2025Q4      # 直接指定季別（建議用此方式）"
    exit 1
fi

if [[ -n "$TARGET_DATE" ]]; then
    year="${TARGET_DATE:0:4}"
    month="${TARGET_DATE:4:2}"
    day="${TARGET_DATE:6:2}"
    month_num=$((10#$month))
    day_num=$((10#$day))

    # 這裡的窗口刻意比 xbrl_scrape_daily.sh 寬（那支起日收到申報期限前 30 天），
    # 兩邊不要同步。scrape 收窄是為了省掉每夜 1.5 小時的空轉爬蟲；這支只是手動
    # 補資料時用今天日期猜季別，收窄只會讓「4 月初想重跑 Q1 入庫」多打一次
    # YYYYQX 參數。
    if (( month_num == 2 || month_num == 3 )); then
        TARGET_QUARTER="$((10#$year - 1))Q4"
    elif (( month_num == 4 )) || (( month_num == 5 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q1"
    elif (( month_num == 7 )) || (( month_num == 8 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q2"
    elif (( month_num == 10 )) || (( month_num == 11 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q3"
    else
        echo "Error: $TARGET_DATE 落在公告窗口外，無法自動決定季別。"
        echo "請改傳 YYYYQX 直接指定，例如：$0 2025Q4"
        exit 1
    fi
fi

if [[ ! "$TARGET_QUARTER" =~ ^([0-9]{4})Q([1-4])$ ]]; then
    echo "Error: invalid target quarter '$TARGET_QUARTER'"
    exit 1
fi

LOG_FILE="$LOG_DIR/xbrl_process_import_${TARGET_QUARTER}_${EXEC_TS}.log"

{
    echo "========================================"
    echo "XBRL Process+Import Started"
    echo "Date: $(date)"
    [[ -n "$TARGET_DATE" ]] && echo "Input Date: $TARGET_DATE"
    echo "Target Quarter: $TARGET_QUARTER"
    echo "FORCE_REPROCESS: ${FORCE_REPROCESS:-0}"
    echo "FORCE_REIMPORT:  ${FORCE_REIMPORT:-0}"
    echo "========================================"
} | tee -a "$LOG_FILE"

run_step() {
    local label="$1"
    shift
    echo "[$label] $*" | tee -a "$LOG_FILE"
    if "$@" 2>&1 | tee -a "$LOG_FILE"; then
        echo "✓ [$label] done" | tee -a "$LOG_FILE"
    else
        echo "✗ [$label] failed" | tee -a "$LOG_FILE"
        exit 1
    fi
}

# 1) Process XBRL（statement-level + quarterly_reports_xbrl）
run_step "1/3 process" \
    docker compose run --rm \
        -e START_DATE="$TARGET_QUARTER" \
        -e END_DATE="$TARGET_QUARTER" \
        -e FORCE_REPROCESS=${FORCE_REPROCESS:-0} \
        processor python convert_quarterly_xbrl.py

# 2) Import statement-level XBRL tables
run_step "2/3 import_xbrl" \
    docker compose run --rm \
        -e START_DATE="$TARGET_QUARTER" \
        -e END_DATE="$TARGET_QUARTER" \
        -e FORCE_REIMPORT=${FORCE_REIMPORT:-0} \
        importer python import_xbrl.py

# 3) Import quarterly_reports_xbrl
run_step "3/3 import_quarterly_xbrl" \
    docker compose run --rm \
        -e START_DATE="$TARGET_QUARTER" \
        -e END_DATE="$TARGET_QUARTER" \
        -e FORCE_REIMPORT=${FORCE_REIMPORT:-0} \
        importer python import_quarterly_xbrl.py

{
    echo "========================================"
    echo "XBRL Process+Import Completed"
    echo "Target Quarter: $TARGET_QUARTER"
    echo "Date: $(date)"
    echo "========================================"
} | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "xbrl_process_import_*.log" -mtime +30 -delete
