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
#
#   推導分兩種情形，取決於申報期限是否已過：
#     已收攤的季別 -> 用該季申報期限日（Q1 0515 / Q2 0815 / Q3 1115 / Q4 隔年 0331）。
#         這種季別的既有檔後綴 100% 統一成這個值（2024Q2 實測 1,645 份全是 _20240815）。
#     期限未到的季別 -> 用「今天」，並標記 [LIVE]。
#         這種季別的 raw 是 xbrl_scrape_daily.sh 每天累積的，後綴本來就分散
#         （2026Q2 累積期間實測散在 _20260807~_20260814），沒有眾數後綴可對齊；
#         而且蓋上未來的期限日會讓 publish_time 早於實際取得日。跟著每日 scrape
#         用「今天」，才與同季其他列一致。日常請直接走 xbrl_scrape_daily.sh。
#
#   真要用別的值再傳 --run-date 覆寫。
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

# 印到 header 註解結束為止（第一個非 # 開頭的行），不寫死行號 —— 寫死的話註解一長
# 就會把底下的 code 一起印進說明裡。
usage() {
    awk 'NR > 1 { if (/^#/) { sub(/^# ?/, ""); print; next } exit }' "$0"
    exit "${1:-1}"
}

require_value() {
    # $1=旗標名 $2=剩餘參數個數。少了這道，旗標放在最後一個位置時
    # `shift 2` 會在 $#=1 失敗，set -e 直接無聲中止。
    if (( $2 < 2 )); then
        echo "Error: $1 requires a value"
        exit 1
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --report-id)
            require_value "$1" "$#"
            REPORT_ID="$2"
            shift 2
            ;;
        --run-date)
            require_value "$1" "$#"
            RUN_DATE_OVERRIDE="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            usage 0
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

# 各季的申報期限日。**已收攤的季別**，該季既有 raw 檔名的後綴就是這個值
# （2024Q2 實測 1,645 份 100% 是 _20240815，Q1/Q3/Q4 同樣統一）。
deadline_for() {
    local y="$1" q="$2"
    case "$q" in
        1) echo "${y}0515" ;;
        2) echo "${y}0815" ;;
        3) echo "${y}1115" ;;
        4) echo "$(( y + 1 ))0331" ;;
        *) echo "Error: bad quarter '$q'" >&2; return 1 ;;
    esac
}

# 申報期限還沒到的季別**不能**用期限日當後綴：那會蓋上一個未來日期，而且該季
# raw 是 xbrl_scrape_daily.sh 每天累積的、後綴本來就分散（2026Q2 累積期間實測
# 散在 _20260807~_20260814），根本沒有「眾數後綴」可對齊。這種季別跟著每日
# scrape 的作法用「今天」，publish_time 才與同季其他列一致。
run_date_for() {
    local y="$1" q="$2" deadline today
    deadline="$(deadline_for "$y" "$q")" || return 1
    today="$(date +%Y%m%d)"
    if (( 10#$deadline > 10#$today )); then
        echo "$today"
    else
        echo "$deadline"
    fi
}

is_live_quarter() {
    local deadline
    deadline="$(deadline_for "$1" "$2")" || return 1
    (( 10#$deadline > 10#$(date +%Y%m%d) ))
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
#
# 只停**這次執行自己啟動的**那一個容器：用 --name 指定含 PID 的專屬名稱並記在
# CURRENT_CONTAINER。不能用 `--filter name=scraper-quarterly-run` 一網打盡 ——
# 那個 pattern 會連同時在跑的另一趟回補一起殺掉（同一台機器上跑兩段不同季別
# 是常見作法，靠 skipped_exists 互不干擾）。
CONTAINER_PREFIX="xbrl-backfill-$$"
CURRENT_CONTAINER=""

cleanup() {
    echo ""
    if [[ -n "$CURRENT_CONTAINER" ]]; then
        echo "[ABORT] 收到中斷訊號，停止 $CURRENT_CONTAINER ..." | tee -a "$LOG_FILE"
        docker stop "$CURRENT_CONTAINER" >/dev/null 2>&1 || true
    else
        echo "[ABORT] 收到中斷訊號（目前沒有執行中的容器）。" | tee -a "$LOG_FILE"
    fi
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

    live_note=""
    if [[ -z "$RUN_DATE_OVERRIDE" ]] && is_live_quarter "$year" "$quarter"; then
        live_note="  [LIVE] 申報期限未到，用今天而非期限日"
    fi

    if [[ "$DRY_RUN" -eq 1 ]]; then
        printf "[DRY] %-8s --report-id %-4s --run-date %s%s\n" \
            "$target" "$REPORT_ID" "$run_date" "$live_note" | tee -a "$LOG_FILE"
    else
        echo "" | tee -a "$LOG_FILE"
        echo "[RUN] $target (report_id=$REPORT_ID run_date=$run_date)$live_note" | tee -a "$LOG_FILE"
        if [[ -n "$live_note" ]]; then
            echo "      這一季仍在累積中，日常請走 ./schedules/xbrl_scrape_daily.sh" | tee -a "$LOG_FILE"
        fi

        CURRENT_CONTAINER="${CONTAINER_PREFIX}-${target}"
        if docker compose run --rm --name "$CURRENT_CONTAINER" \
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
        CURRENT_CONTAINER=""
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
