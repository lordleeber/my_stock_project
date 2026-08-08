#!/bin/bash
# 季報 XBRL 每日 scrape（公告期內持續累積 raw 資料；不跑 process / import）
#
# 抓取窗口（起日一律 = 申報期限前 30 天；結束日 = 申報期限，Q2/Q3 多留一天）：
#   Q4 (前一年):   03/01 ~ 03/31   期限 03/31
#   Q1 (同年):     04/15 ~ 05/15   期限 05/15
#   Q2 (同年):     07/15 ~ 08/15   期限 08/14，多留一天
#   Q3 (同年):     10/15 ~ 11/15   期限 11/14，多留一天
#   其他日期：     skip
#
# 起日取 T-30 而不是月初：整份名單掃一輪要 1,849 檔 × 3 秒 ≈ 1.5 小時，而逐日
# 資料顯示最早的申報落在 T-32(2026Q1)、T-16(2026Q2)——2026Q2 那次從 07/01 開窗
# 到 07/29 才抓到第一份，中間 28 夜共約 5.2 萬次請求全部回「檔案不存在」。
# (2025Q4 年報最早的 raw 是 03/03，但那天一次進 196 檔、2 月的 log 已不存在，
# 無法確認 2 月到底有沒有跑，所以那個 T-28 是推論不是量測。)
# 晚開窗不會漏資料：MOPS 給的是當下累積狀態，dedupe key 又是 symbol 而非日期，
# 開窗第一夜就會把先前已公告的一次補齊；XBRL 的 publish_time(=抓取日) 也沒有
# 任何下游拿去做 PIT 判斷。少掃這幾十夜同時降低被 MOPS 擋的機率，而被擋最貴的
# 時間點正是期限前那一週。
#
# 結束日不隨起日一起調。Q2/Q3 之所以多留一天到 15 號，是為了對齊
# train_eps/shared_config.py 的 cutoff（5/15、8/15、11/15）：窗口最後一夜抓到的
# 財報，隔天 16 號的 playbook 正好吃得到，往後延的資料當月 walk-forward 用不到。
# Q4 沒有這個對齊問題——年報期限 03/31 本來就晚於 3 月的 cutoff(03/10)，那批資料
# 要等 4/11 的 playbook 才用得到，所以結束日直接收在期限當天。
# （金融業申報期限較晚、必然落在窗口外，但那是 converter 不支援金融業科目表的
# 問題，延窗口也換不到 DB 資料——見 KNOWN_ISSUES.md。）
#
# DB 入庫由 `xbrl_process_import.sh` 手動觸發（公告期末 / 補資料時）。

set -euo pipefail

cd "$(dirname "$0")/.."

./schedules/ensure_error_logs.sh

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
EXEC_TS=$(date +%Y%m%d_%H%M%S)

ARG1="${1:-}"
TARGET_DATE=""
TARGET_QUARTER=""
SKIP_MODE=0

if [[ -z "$ARG1" ]]; then
    TARGET_DATE="$(date +%Y%m%d)"
elif [[ "$ARG1" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    TARGET_QUARTER="$ARG1"
elif [[ "$ARG1" =~ ^[0-9]{8}$ ]]; then
    TARGET_DATE="$ARG1"
else
    echo "Usage: $0 [YYYYMMDD|YYYYQX]"
    exit 1
fi

if [[ -n "$TARGET_DATE" ]]; then
    year="${TARGET_DATE:0:4}"
    month="${TARGET_DATE:4:2}"
    day="${TARGET_DATE:6:2}"
    month_num=$((10#$month))
    day_num=$((10#$day))

    if (( month_num == 3 )); then
        TARGET_QUARTER="$((10#$year - 1))Q4"
    elif (( month_num == 4 && day_num >= 15 )) || (( month_num == 5 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q1"
    elif (( month_num == 7 && day_num >= 15 )) || (( month_num == 8 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q2"
    elif (( month_num == 10 && day_num >= 15 )) || (( month_num == 11 && day_num <= 15 )); then
        TARGET_QUARTER="${year}Q3"
    else
        SKIP_MODE=1
    fi
fi

if [[ "$SKIP_MODE" -eq 1 ]]; then
    LOG_FILE="$LOG_DIR/xbrl_scrape_skip_${EXEC_TS}.log"
else
    if [[ ! "$TARGET_QUARTER" =~ ^([0-9]{4})Q([1-4])$ ]]; then
        echo "Error: invalid target quarter '$TARGET_QUARTER'"
        exit 1
    fi
    LOG_FILE="$LOG_DIR/xbrl_scrape_${TARGET_QUARTER}_${EXEC_TS}.log"
fi

if [[ "$SKIP_MODE" -eq 1 ]]; then
    {
        echo "========================================"
        echo "XBRL Scrape Skipped"
        echo "Date: $(date)"
        echo "Input Date: $TARGET_DATE"
        echo "Outside XBRL fetch windows."
        echo "========================================"
    } | tee -a "$LOG_FILE"
    exit 0
fi

REPORT_YEAR="${BASH_REMATCH[1]}"
REPORT_QUARTER="${BASH_REMATCH[2]}"

{
    echo "========================================"
    echo "XBRL Scrape Started"
    echo "Date: $(date)"
    [[ -n "$TARGET_DATE" ]] && echo "Input Date: $TARGET_DATE"
    echo "Target Quarter: $TARGET_QUARTER"
    echo "FORCE_REPROCESS: ${FORCE_REPROCESS:-0}"
    echo "========================================"
} | tee -a "$LOG_FILE"

if docker compose run --rm \
    -e FORCE_REPROCESS=${FORCE_REPROCESS:-0} \
    scraper-quarterly \
    python3 scraper/quarterly/fetch_xbrl.py --year "$REPORT_YEAR" --quarter "$REPORT_QUARTER" 2>&1 | tee -a "$LOG_FILE"; then
    echo "✓ XBRL scrape done" | tee -a "$LOG_FILE"
else
    echo "✗ XBRL scrape failed" | tee -a "$LOG_FILE"
    exit 1
fi

{
    echo "========================================"
    echo "XBRL Scrape Completed"
    echo "Target Quarter: $TARGET_QUARTER"
    echo "Date: $(date)"
    echo "========================================"
} | tee -a "$LOG_FILE"

find "$LOG_DIR" -name "xbrl_scrape_*.log" -mtime +30 -delete
