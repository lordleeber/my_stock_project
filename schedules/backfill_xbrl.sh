#!/bin/bash
#
# 多季 XBRL raw 補齊（只跑 scrape 階段，不含 processor/importer）。
# 補完後對每季呼叫 ./schedules/xbrl_process_import.sh 入庫。
#
# 用法：
#   ./schedules/backfill_xbrl.sh <START_QUARTER> <END_QUARTER> [OPTIONS]
#
#   --report-id {auto,C,A}   報表別。預設 auto（對齊 fetch_xbrl.py）
#   --run-date YYYYMMDD      覆寫檔名後綴。預設依季別自動推導（見下）
#   --dry-run                只印出每季會用的參數，不送任何請求
#
# 例：
#   ./schedules/backfill_xbrl.sh 2021Q2 2025Q3
#   ./schedules/backfill_xbrl.sh 2020Q1 2026Q2 --report-id A
#   ./schedules/backfill_xbrl.sh 2020Q1 2026Q2 --dry-run
#
# --run-date 為什麼必須依季別推導
#   這個後綴就是 processor 從檔名讀出來的 publish_time。舊版沒傳它，fetch_xbrl.py
#   會退成「執行當天」—— 拿去回補 2020Q1 會產生 2020Q1_1342_20260816.html，而該季
#   既有檔是 _20200515。後果有兩層：publish_time 在同一季自相矛盾；檔名不同導致
#   collect_strict_html_per_symbol() 判定「同季同 symbol 兩個 html」而**整季 raise**。
#   所以預設改成各季的申報期限日（Q1 0515 / Q2 0815 / Q3 1115 / Q4 隔年 0331），
#   與該季既有檔的眾數後綴一致。真要用別的值再傳 --run-date 覆寫。
#
# --report-id 怎麼選
#   auto  先合併(C)，回報「尚未申報」再退個體(A)。日常與不確定時用這個。
#   C     只抓合併。災難重建的第一趟（空目錄）用這個 —— 見下。
#   A     只抓個體。合併財報已在磁碟上、只補個體時用，可省一半請求。
#
#   ⚠️ 空目錄不要用 A：save_symbol_report 只對「完全沒有檔」的 symbol 送請求，
#      用 A 跑空目錄會只拿到個體財報、漏掉全部合併財報。
#   ⚠️ 空目錄用 auto 也拿不到個體財報：個體 fallback 受
#      INDIVIDUAL_FALLBACK_MIN_COVERAGE=0.60 管制，而 coverage 是「開跑時磁碟已有
#      檔數 ÷ 掃描宇宙」只算一次（fetch_xbrl.py:500）。空目錄 = 0% < 60%，auto 會
#      退成 C-only。所以從零重建一律兩趟：先 --report-id C，再 --report-id A。

set -euo pipefail

cd "$(dirname "$0")/.."

./schedules/ensure_error_logs.sh

START_QUARTER=""
END_QUARTER=""
REPORT_ID="auto"
RUN_DATE_OVERRIDE=""
DRY_RUN=0

usage() {
    sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --report-id)
            REPORT_ID="${2:-}"
            shift 2
            ;;
        --run-date)
            RUN_DATE_OVERRIDE="${2:-}"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage
            ;;
        -*)
            echo "Error: unknown option '$1'"
            exit 1
            ;;
        *)
            if [[ -z "$START_QUARTER" ]]; then
                START_QUARTER="$1"
            elif [[ -z "$END_QUARTER" ]]; then
                END_QUARTER="$1"
            else
                echo "Error: unexpected argument '$1'"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$START_QUARTER" || -z "$END_QUARTER" ]]; then
    usage
fi

if ! [[ "$START_QUARTER" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    echo "Error: invalid START_QUARTER '$START_QUARTER' (expected YYYYQX)"
    exit 1
fi

if ! [[ "$END_QUARTER" =~ ^[0-9]{4}Q[1-4]$ ]]; then
    echo "Error: invalid END_QUARTER '$END_QUARTER' (expected YYYYQX)"
    exit 1
fi

if ! [[ "$REPORT_ID" =~ ^(auto|C|A)$ ]]; then
    echo "Error: invalid --report-id '$REPORT_ID' (expected auto, C or A)"
    exit 1
fi

if [[ -n "$RUN_DATE_OVERRIDE" ]] && ! [[ "$RUN_DATE_OVERRIDE" =~ ^[0-9]{8}$ ]]; then
    echo "Error: invalid --run-date '$RUN_DATE_OVERRIDE' (expected YYYYMMDD)"
    exit 1
fi

start_year="${START_QUARTER:0:4}"
start_q="${START_QUARTER:5:1}"
end_year="${END_QUARTER:0:4}"
end_q="${END_QUARTER:5:1}"

if (( 10#$start_year > 10#$end_year )) || { (( 10#$start_year == 10#$end_year )) && (( 10#$start_q > 10#$end_q )); }; then
    echo "Error: START_QUARTER must be <= END_QUARTER"
    exit 1
fi

# 各季的申報期限日 = 該季既有 raw 檔名的眾數後綴（2020Q1~2025Q3 全季實測統一）。
run_date_for() {
    local y="$1" q="$2"
    case "$q" in
        1) echo "${y}0515" ;;
        2) echo "${y}0815" ;;
        3) echo "${y}1115" ;;
        4) echo "$(( y + 1 ))0331" ;;
        *) echo "Error: bad quarter '$q'" >&2; return 1 ;;
    esac
}

if [[ -n "$RUN_DATE_OVERRIDE" && "$START_QUARTER" != "$END_QUARTER" ]]; then
    echo "[WARN] --run-date $RUN_DATE_OVERRIDE 會套用到範圍內**每一季**，"
    echo "       這通常只在單季時才是你要的。不確定就拿掉它、讓各季自動推導。"
fi

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/backfill_xbrl_${START_QUARTER}_${END_QUARTER}_$(date +%Y%m%d_%H%M%S).log"

# Ctrl+C 對 `docker compose run` 只殺得掉本機 client，容器會被 containerd 收養
# 繼續跑（實測：孤兒容器仍在對 MOPS 送請求，得手動 docker stop）。這裡攔下訊號
# 主動收掉容器，讓 Ctrl+C 的行為符合預期 —— 這支動輒跑幾十小時，叫得停是必要的。
cleanup() {
    echo ""
    echo "[ABORT] 收到中斷訊號，停止 scraper 容器..." | tee -a "$LOG_FILE"
    docker ps --filter "name=scraper-quarterly-run" -q | xargs -r docker stop >/dev/null 2>&1 || true
    echo "[ABORT] 已停止。已抓到的檔案保留，原樣重跑會跳過它們。" | tee -a "$LOG_FILE"
    exit 130
}
trap cleanup INT TERM

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Backfill Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Range: $START_QUARTER ~ $END_QUARTER" | tee -a "$LOG_FILE"
echo "report_id: $REPORT_ID" | tee -a "$LOG_FILE"
echo "run_date: ${RUN_DATE_OVERRIDE:-auto (依季別推導)}" | tee -a "$LOG_FILE"
echo "FORCE_REPROCESS: ${FORCE_REPROCESS:-0}" | tee -a "$LOG_FILE"
[[ "$DRY_RUN" -eq 1 ]] && echo "DRY RUN: 不會送出任何請求" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

year=$((10#$start_year))
quarter=$((10#$start_q))
end_year_num=$((10#$end_year))
end_q_num=$((10#$end_q))
FAILED_QUARTERS=()

while (( year < end_year_num || (year == end_year_num && quarter <= end_q_num) )); do
    target="${year}Q${quarter}"
    run_date="${RUN_DATE_OVERRIDE:-$(run_date_for "$year" "$quarter")}"

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf "[DRY] %-8s --report-id %-4s --run-date %s\n" \
            "$target" "$REPORT_ID" "$run_date" | tee -a "$LOG_FILE"
    else
        echo "" | tee -a "$LOG_FILE"
        echo "[RUN] $target (report_id=$REPORT_ID run_date=$run_date)" | tee -a "$LOG_FILE"

        if docker compose run --rm \
            -e FORCE_REPROCESS=${FORCE_REPROCESS:-0} \
            scraper-quarterly \
            python3 scraper/quarterly/fetch_xbrl.py \
            --year "$year" --quarter "$quarter" \
            --report-id "$REPORT_ID" --run-date "$run_date" 2>&1 | tee -a "$LOG_FILE"; then
            echo "[OK] $target" | tee -a "$LOG_FILE"
        else
            echo "[FAIL] $target" | tee -a "$LOG_FILE"
            FAILED_QUARTERS+=("$target")
        fi
    fi

    quarter=$((quarter + 1))
    if (( quarter > 4 )); then
        quarter=1
        year=$((year + 1))
    fi
done

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Backfill Completed" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"

if [ ${#FAILED_QUARTERS[@]} -gt 0 ]; then
    echo "Failed Quarters (${#FAILED_QUARTERS[@]}): ${FAILED_QUARTERS[*]}" | tee -a "$LOG_FILE"
    echo "========================================" | tee -a "$LOG_FILE"
    exit 1
fi

echo "========================================" | tee -a "$LOG_FILE"
