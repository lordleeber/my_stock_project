import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.error_log import append_error_log as append_to_error_log  # noqa: E402

ERROR_LOG = "error_scraper.log"

BASE_URL = "https://mopsov.twse.com.tw/server-java/t164sb01"
ACTIVE_STOCKS_FILE = Path("active_stocks.txt")
OUTPUT_ROOT = Path("data/raw/xbrl")
MAX_RETRIES = 0

# 對 MOPS 送出兩次請求之間的間隔。2026-07-02 被封鎖之後定下的節奏，別縮短。
FETCH_INTERVAL_SECONDS = 3

# MOPS t164sb01 的報表別。
#   C = 合併財報、A = 個體財報。
# 台灣規定無子公司者免編合併財務報表、以個體財報申報，所以這類公司對 C 查詢
# 一律回「檔案不存在」（97 bytes）。舊版把 REPORT_ID 寫死成 C，於是它們從 2020 年
# 起完全不在資料庫裡 —— 2026-08-16 實測非金融 167 檔中有 165 檔只有個體財報，
# 佔選股宇宙 10%（台灣高鐵、寶雅、采鈺、精材、昇佳電子、宏捷科…）。
# 兩者對同一 symbol 同一季互斥（實測 2330／富邦金雙向驗證），所以永遠只會存一份，
# 檔名格式因此維持不變，processor 的「同季同 symbol 禁止兩個 html」規則不受影響。
#
# 報表別不編進檔名，因為報表內容自帶 tifrs-notes:ReportCategory
# （Consolidated report / Individual report）。但**目前下游還沒有人讀它** ——
# 個體財報進到 *_xbrl 後與合併財報無從分辨，而個體財報沒有 8610（歸屬母公司
# 業主淨利），總資產／總權益也是母公司單體基礎。接手判讀與 net_income 取數是
# 下一個 PR 的事，在那之前不要假設下游分得出來。
REPORT_ID_CONSOLIDATED = "C"
REPORT_ID_INDIVIDUAL = "A"
REPORT_ID_FALLBACK_CHAIN = (REPORT_ID_CONSOLIDATED, REPORT_ID_INDIVIDUAL)

# 只有「這個報表別尚未申報」才值得換另一個報表別再試一次。rate_limit /
# page_not_accessible 是站方狀態，換 REPORT_ID 照樣被擋，徒然多打一次請求，
# 還會拖慢 RATE_LIMIT_ABORT_STREAK 收手的速度。
FALLBACK_TRIGGER_REASON = "report_not_published"

# 啟動個體財報 fallback 的門檻：本季已收到的報表數 / 掃描宇宙。
#
# 申報期限**之前**，C 回「尚未申報」代表的就是「還沒到期」—— 這種公司若是個體
# 申報，A 同樣還沒申報，多打一次純屬浪費。而 scrape 窗口一開就是期限前 30 天，
# 那幾夜幾乎整批 report_not_published：2026-08-01 那夜 1,763 檔，每檔多一次請求
# 加 3 秒間隔就是多出約 88 分鐘。xbrl scrape 23:50 起跑、stock-daily-retry 03:00
# 觸發，這樣壓過去會直接吃掉 retry 的時間。
#
# 用「本季已收到多少」判斷窗口尾端，比在這裡再抄一份申報期限日期表可靠 ——
# 那份表在 schedules/xbrl_scrape_daily.sh，而且刻意與 xbrl_process_import.sh
# 的窗口不同步（見兩支 script 的註解），多一份副本遲早會走鐘。
#
# 2026Q2 實測逐夜覆蓋率：08-01 0% → 08-06 10% → 08-11 28% → 08-13 53% →
# 08-14 72% → 08-15 89%。門檻取 0.80 只在 08-15 那夜觸發，正是 A 探測唯一
# 有意義的時點（08-14 的 510 次無謂探測也一併省下）。
#
# 天花板意識：C 收得到的比例就是覆蓋率上限（2026Q2 = 1,645/1,851 ≈ 89%）。
# 個體申報的占比若從現在的 ~9% 漲到 20% 以上，這個門檻就再也達不到、個體財報
# 會收不進來 —— 屆時要調低。啟用與否每次執行都印在 log 開頭，不會默默失效。
# 回補歷史季別請直接用 --report-id A，不受本門檻影響。
INDIVIDUAL_FALLBACK_MIN_COVERAGE = 0.80

# 正常的 inline XBRL 季報一定帶這兩個 namespace 之一；MOPS 的各式錯誤頁
# （安全性阻擋頁、「檔案不存在!」、rate limit 頁）都沒有。
# 2026-08-01 對 data/raw/xbrl 全量 41,158 檔驗證：>= 2 KB 的 39,328 檔 100% 命中，0 例外。
XBRL_MARKERS = (
    "http://www.xbrl.org/2003/instance",
    "http://www.xbrl.org/2013/inlineXBRL",
)

# 報表大小下限（寫入磁碟的 utf-8 bytes）。同一次全量驗證：最小的正常報表
# 351,319 bytes（2026Q1），沒有任何一份正常報表 < 200 KB；對照組是
# 安全性阻擋頁 800 bytes、「檔案不存在!」97 bytes。取 100 KB，兩邊都留數量級餘裕。
MIN_REPORT_BYTES = 100_000

# 掃描既有檔案時只讀檔頭找 marker（namespace 都在最前面幾百 bytes）。
HEAD_SCAN_BYTES = 8192

# 連續幾次 rate_limit 就中止本次執行。取 5 是為了不被單一次誤判打斷，
# 又能在真的被封鎖時立刻收手（而不是把剩下 1,800 個 symbol 全部打完）。
RATE_LIMIT_ABORT_STREAK = 5

# 這些失敗是預期中的，不代表故障，不該影響退出碼。
# report_not_published：該季報還沒申報（例如 8/14 前抓 Q2），等下次排程即可。
BENIGN_FAILURE_REASONS = frozenset({"report_not_published"})


def append_error_log(
    year: int, quarter: int, run_date: str, failures: list[tuple[str, str]]
):
    if not failures:
        return
    append_to_error_log(
        ERROR_LOG,
        "scraper-quarterly-detail-xbrl failures",
        [
            f"Quarter: {year}Q{quarter}",
            f"run_date: {run_date}",
            f"failed_count: {len(failures)}",
        ]
        + [f"- {symbol}: {status}" for symbol, status in failures],
    )


def load_symbols(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"active stocks file not found: {path}")

    symbols: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            symbol = line.strip()
            if re.match(r"^\d{4}$", symbol):
                symbols.append(symbol)
    return symbols


def parse_run_date(raw: str | None) -> str:
    """決定寫進檔名的 YYYYMMDD 後綴。

    這個後綴不是裝飾：processor 就是從檔名解析 publish_time
    （processor/CLAUDE.md「publish_time source rule (strict)」）。回補歷史季別時
    若沿用「今天」，2020Q1 會多出一批 publish_time=2026xxxx 的列，與該季既有資料
    （整季統一為申報期限）自相矛盾。所以要能明確指定，而且必須是合法日期 ——
    20261332 這種過得了 \\d{8} 卻不存在的值要當場擋掉，不能讓它寫進檔名。
    """
    if raw is None:
        return datetime.now().strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", raw):
        raise ValueError(f"--run-date 必須是 YYYYMMDD，收到 {raw!r}")
    try:
        datetime.strptime(raw, "%Y%m%d")
    except ValueError as e:
        raise ValueError(f"--run-date 不是合法日期: {raw}") from e
    return raw


def fetch_xbrl_html(
    symbol: str,
    year: int,
    quarter: int,
    report_id: str = REPORT_ID_CONSOLIDATED,
    timeout: int = 30,
) -> bytes:
    params = {
        "step": 1,
        "CO_ID": symbol,
        "SYEAR": year,
        "SSEASON": quarter,
        "REPORT_ID": report_id,
    }
    url = f"{BASE_URL}?{urlencode(params)}"
    # Use curl to match the environment behavior already verified manually.
    cp = subprocess.run(
        [
            "curl",
            "-sL",
            "--max-time",
            str(timeout),
            "-A",
            "Mozilla/5.0",
            url,
        ],
        capture_output=True,
        check=False,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"curl_failed:{cp.returncode}")
    return cp.stdout


def decode_to_utf8(raw: bytes) -> str:
    # MOPS pages are usually Big5/cp950.
    for enc in ("cp950", "big5", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp950", errors="replace")


def validate_report(html_text: str) -> str | None:
    """回傳失敗原因；None 代表看起來是一份正常的 XBRL 季報。

    這是「能不能存檔」的唯一關卡，而且刻意採正向驗證：先前的作法是逐條列舉
    MOPS 的錯誤頁字樣，結果兩個 marker 各差一個字（the/this、執行/呈現），
    安全性阻擋頁就整批被當成正常回應存檔。要求回應具備季報應有的特徵，
    比窮舉錯誤樣式難漏；MOPS 新增或改寫錯誤頁也不必跟著追。
    """
    if len(html_text.encode("utf-8")) < MIN_REPORT_BYTES:
        return "too_small"
    lower = html_text.lower()
    if "<html" not in lower:
        return "invalid_html"
    if not any(marker.lower() in lower for marker in XBRL_MARKERS):
        return "no_xbrl_markers"
    return None


def classify_failure_reason(html_text: str) -> str | None:
    """辨識 MOPS 回應的類型，只用於把失敗原因寫得更清楚。

    存檔與否一律由 validate_report() 決定，這裡漏判不會讓壞資料落地。
    """
    lower = html_text.lower()
    marker_reason_pairs = [
        # 實際訊息是 "OVERRUN - 查詢過於頻繁,請稍後再試"，只比對核心片語。
        ("查詢過於頻繁", "rate_limit"),
        ("too many query requests from your ip", "rate_limit"),
        # 不含冠詞，避免再被 the/this 這種一字之差絆倒。
        ("page can not be accessed", "page_not_accessible"),
        ("因為安全性考量", "page_not_accessible"),
        ("頁面無法呈現", "page_not_accessible"),
        ("頁面無法執行", "page_not_accessible"),
        # 該季報尚未申報（例如申報期限前來抓）。不是故障，等下次排程即可。
        ("檔案不存在", "report_not_published"),
    ]
    for marker, reason in marker_reason_pairs:
        if marker.lower() in lower:
            return reason
    return None


def base_status(status: str) -> str:
    """去掉 save_symbol_report() 失敗時附加的 ";retries=N" 後綴。"""
    return status.split(";", 1)[0]


def saved_status(report_id: str) -> str:
    """存檔成功時的狀態字串。

    合併財報維持 "ok" 不變（既有 log 與人的肌肉記憶都吃這個字），個體財報標成
    "ok_a"，讓收尾統計看得出這一季有幾檔是靠 fallback 收進來的。
    """
    if report_id == REPORT_ID_CONSOLIDATED:
        return "ok"
    return f"ok_{report_id.lower()}"


def resolve_report_ids(requested: str, coverage: float) -> tuple[tuple[str, ...], str]:
    """決定這次要依序嘗試哪些報表別，並附一句寫進 log 的理由。

    `auto` 之下個體財報的 fallback 只在本季已大致收齊時才啟用 ——
    理由與門檻的推導見 INDIVIDUAL_FALLBACK_MIN_COVERAGE。
    """
    if requested != "auto":
        return (requested,), "explicit"

    pct = f"coverage {coverage:.0%}"
    threshold = f"{INDIVIDUAL_FALLBACK_MIN_COVERAGE:.0%}"
    if coverage >= INDIVIDUAL_FALLBACK_MIN_COVERAGE:
        return REPORT_ID_FALLBACK_CHAIN, f"{pct} >= {threshold}，個體 fallback 啟用"
    return (
        (REPORT_ID_CONSOLIDATED,),
        f"{pct} < {threshold}，個體 fallback 未啟用（申報期限前，A 一樣還沒申報）",
    )


def is_saved_status(reason: str) -> bool:
    """這個 base status 代表「有一份報表落地」嗎？

    存檔成功的字串不只一種（見 saved_status），計數與退出碼都得認得全部，
    否則 fallback 收回來的檔會被算成失敗。
    """
    return reason == "ok" or reason.startswith("ok_")


def decide_exit_code(saved: int, fail: int, non_benign_fail: int, aborted: bool) -> int:
    """決定退出碼，讓 schedules/xbrl_scrape_daily.sh 能觸發 systemd 失敗通知。

    舊版是 `0 if ok > 0 else 1`，而 ok 把 skipped_exists 也算進去，於是只要
    目錄裡還有舊檔就永遠 exit 0 —— MOPS 改版導致每一次抓取都驗證失敗時，
    資料蒐集會靜悄悄停擺而完全不告警。

    條件刻意收得很緊：「這次有嘗試抓取、沒有任何一次成功，而且失敗全都不是
    良性原因」。申報期限前整批 report_not_published 是正常的（例如 8/14 前
    抓 Q2），少數幾檔 curl 暫時失敗也不該每晚叫一次 —— 會叫到沒人理。
    真正要抓的是 MOPS 改版之類「每一次抓取都驗證失敗」的系統性狀況。
    """
    if aborted:
        return 1
    if saved == 0 and fail > 0 and non_benign_fail == fail:
        return 1
    return 0


def strip_run_date_suffix(filename: str) -> str:
    # Convert YYYYQX_1234_YYYYMMDD.html -> YYYYQX_1234.html
    return re.sub(r"_\d{8}(?=\.html$)", "", filename)


def is_valid_report_file(path: Path) -> bool:
    """既有檔案看起來是不是一份正常季報。

    先跑便宜的檢查（size + 檔頭 marker）擋掉絕大多數情形——整季約 1,600 份、
    每份約 500 KB，全讀進來只為了 dedupe 太浪費。只有在檔案夠大、檔頭卻找不到
    marker 時才整份讀進來交給 validate_report()，讓「有效」只有一套定義：
    否則 marker 落在 HEAD_SCAN_BYTES 之後的報表會被判為沒抓過，每晚重抓、
    每晚成功、每晚又被判沒抓過。
    """
    try:
        if path.stat().st_size < MIN_REPORT_BYTES:
            return False
        with path.open("rb") as f:
            head = f.read(HEAD_SCAN_BYTES).lower()
        if any(marker.lower().encode("utf-8") in head for marker in XBRL_MARKERS):
            return True
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return validate_report(text) is None


def load_existing_report_names(out_dir: Path) -> set[str]:
    """已存在「且內容有效」的報表檔名（去掉 run_date 後綴）。

    只認有效檔案是刻意的：壞檔不列入 dedupe key，下次執行才會重抓。先前不分
    好壞一律視為已抓過，導致 2026Q2 存進 1,805 個阻擋頁後就永遠 SKIP，
    除非帶 --force 或手動刪檔，錯一次就卡死。
    """
    names: set[str] = set()
    for path in out_dir.glob("*.html"):
        if is_valid_report_file(path):
            names.add(strip_run_date_suffix(path.name))
    return names


def purge_sibling_reports(
    out_dir: Path,
    year: int,
    quarter: int,
    symbol: str,
    keep: Path,
    include_valid: bool = False,
) -> list[Path]:
    """刪掉同一 symbol 底下其餘的 html，回傳被刪的路徑。

    重抓成功後一定要清掉舊檔，否則自癒反而會弄壞下游：processor 的
    collect_strict_html_per_symbol() 對同季同 symbol 出現兩個檔案是直接
    raise、整季轉檔中止的（processor/CLAUDE.md「multiple html files are
    forbidden」）。壞檔不列入 dedupe key 會讓它被重抓，新檔帶新的 run_date
    後綴，兩個檔案就並存了。

    `include_valid` 只在 FORCE_REPROCESS 時打開。平常抓取遇到已存在的有效檔
    會直接 skip、根本不會走到這裡，所以預設只清壞檔、不動有效檔；但 force 是
    刻意覆寫，此時舊的有效檔若留著就正好湊成「同季同 symbol 兩個 html」，
    整季轉檔會當場中止 —— 尤其 force 搭 --run-date 改後綴時新舊檔名必然不同，
    百分之百踩中。force 之後這個目錄對該 symbol 只會剩下剛寫入的那一份。
    """
    prefix = f"{year}Q{quarter}_{symbol}"
    # 只認 <quarter>_<symbol>.html 與 <quarter>_<symbol>_<YYYYMMDD>.html，
    # 避免 glob 的前綴比對誤傷其他 symbol。
    name_re = re.compile(rf"^{re.escape(prefix)}(?:_\d{{8}})?\.html$")
    removed: list[Path] = []
    for path in out_dir.glob(f"{prefix}*.html"):
        if path == keep or not name_re.match(path.name):
            continue
        if not include_valid and is_valid_report_file(path):
            continue
        try:
            path.unlink()
        except OSError as e:
            print(f"[WARN] {symbol} -> 無法刪除舊檔 {path.name}: {e}")
            continue
        removed.append(path)
    return removed


def save_symbol_report(
    symbol: str,
    year: int,
    quarter: int,
    run_date: str,
    out_dir: Path,
    existing_report_names: set[str],
    force: bool = False,
    report_ids: tuple[str, ...] = REPORT_ID_FALLBACK_CHAIN,
    fetcher=fetch_xbrl_html,
) -> tuple[str, str]:
    """抓一份季報存檔，依序嘗試 `report_ids` 裡的報表別。

    `fetcher` 可注入純為了測試（預設就是真的 `fetch_xbrl_html`）—— fallback 的
    分支條件是這次改動的核心，不能只靠實跑 MOPS 來驗。
    """
    base_filename = f"{year}Q{quarter}_{symbol}.html"
    filename = f"{year}Q{quarter}_{symbol}_{run_date}.html"
    out_path = out_dir / filename
    if not force and base_filename in existing_report_names:
        print(f"[SKIP] {symbol} -> skipped_exists ({base_filename})")
        return symbol, "skipped_exists"

    attempts = MAX_RETRIES + 1
    last_status = "error:unknown"
    for chain_idx, report_id in enumerate(report_ids):
        if chain_idx:
            # 換報表別等同再送一次請求，照正常間隔走；否則這些 symbol 的瞬時請求
            # 速率會是別人的兩倍，正是 2026-07-02 被封鎖的那種打法。
            time.sleep(FETCH_INTERVAL_SECONDS)
        for attempt in range(1, attempts + 1):
            try:
                print(
                    f"[FETCH] {symbol} REPORT_ID={report_id} "
                    f"(attempt {attempt}/{attempts})"
                )
                raw_html = fetcher(symbol, year, quarter, report_id)
                html_text = decode_to_utf8(raw_html)
                invalid_reason = validate_report(html_text)
                if invalid_reason:
                    # 能認出是哪種 MOPS 回應就用它（report_not_published 只是還沒申報，
                    # 不是故障），認不出來才退回 validate_report 的結構性原因。
                    last_status = (
                        classify_failure_reason(html_text)
                        or f"invalid_report:{invalid_reason}"
                    )
                    print(f"[FAIL] {symbol} REPORT_ID={report_id} -> {last_status}")
                else:
                    out_path.write_text(html_text, encoding="utf-8")
                    existing_report_names.add(base_filename)
                    for stale in purge_sibling_reports(
                        out_dir, year, quarter, symbol, out_path, include_valid=force
                    ):
                        print(f"[CLEAN] {symbol} -> removed stale {stale.name}")
                    print(f"[SAVE] {symbol} REPORT_ID={report_id} -> {filename}")
                    return symbol, saved_status(report_id)
            except Exception as e:
                last_status = f"error:{e}"
                print(f"[FAIL] {symbol} REPORT_ID={report_id} -> {last_status}")

                if attempt < attempts:
                    time.sleep(0.3 * attempt)

        if base_status(last_status) != FALLBACK_TRIGGER_REASON:
            break

    return symbol, f"{last_status};retries={MAX_RETRIES}"


def main():
    parser = argparse.ArgumentParser(
        description="Fetch detailed quarterly XBRL HTML reports from MOPS."
    )
    parser.add_argument("--year", type=int, required=True, help="AD year, e.g. 2025")
    parser.add_argument(
        "--quarter", type=int, required=True, choices=[1, 2, 3, 4], help="Quarter 1~4"
    )
    parser.add_argument(
        "--run-date",
        help=(
            "覆寫檔名的 YYYYMMDD 後綴（預設今天）。回補歷史季別時務必指定該季的"
            "申報期限：這個後綴就是 processor 讀出來的 publish_time，用回補當天"
            "的日期會讓 2020Q1 冒出一批 2026 年的 publish_time。"
        ),
    )
    parser.add_argument(
        "--report-id",
        choices=["auto", REPORT_ID_CONSOLIDATED, REPORT_ID_INDIVIDUAL],
        default="auto",
        help=(
            "auto（預設）= 先合併(C)、回報「尚未申報」再退到個體(A)。"
            f"指定 {REPORT_ID_INDIVIDUAL} 可直接跑個體財報單趟 —— 回補早已過了"
            "申報期限的歷史季別時，C 必定不存在，跳過它可省一半請求。"
        ),
    )
    args = parser.parse_args()
    force_reprocess = os.getenv("FORCE_REPROCESS", "0") == "1"

    symbols = load_symbols(ACTIVE_STOCKS_FILE)
    if not symbols:
        print("No valid symbols found in active_stocks.txt")
        return 1

    try:
        run_date = parse_run_date(args.run_date)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    quarter_key = f"{args.year}Q{args.quarter}"
    out_dir = OUTPUT_ROOT / str(args.year) / quarter_key
    out_dir.mkdir(parents=True, exist_ok=True)
    existing_report_names = load_existing_report_names(out_dir)

    coverage = len(existing_report_names) / len(symbols)
    report_ids, chain_note = resolve_report_ids(args.report_id, coverage)

    print(f"Target quarter: {quarter_key}")
    print(f"Symbols: {len(symbols)}")
    print(f"Output: {out_dir}")
    print(f"run_date: {run_date}")
    print(f"report_id: {args.report_id} -> chain {','.join(report_ids)} ({chain_note})")
    print(f"existing_reports: {len(existing_report_names)}")
    print(
        f"overwrite: {'enabled' if force_reprocess else 'disabled'} (FORCE_REPROCESS)"
    )

    saved = 0
    skipped = 0
    fail = 0
    non_benign_fail = 0
    rate_limit_streak = 0
    aborted = False
    status_count: dict[str, int] = {}
    failures: list[tuple[str, str]] = []

    for idx, symbol in enumerate(symbols, start=1):
        symbol, status = save_symbol_report(
            symbol,
            args.year,
            args.quarter,
            run_date,
            out_dir,
            existing_report_names,
            force=force_reprocess,
            report_ids=report_ids,
        )
        status_count[status] = status_count.get(status, 0) + 1
        reason = base_status(status)
        if is_saved_status(reason):
            saved += 1
        elif reason == "skipped_exists":
            skipped += 1
        else:
            fail += 1
            failures.append((symbol, status))
            if reason not in BENIGN_FAILURE_REASONS:
                non_benign_fail += 1

        # 連續被 rate limit 就收手。2026-07-02 就是一路跑完 1,800 個 symbol，
        # 把整季寫成阻擋頁；繼續打只會讓封鎖延長，該季隔天再試即可。
        if reason == "rate_limit":
            rate_limit_streak += 1
            if rate_limit_streak >= RATE_LIMIT_ABORT_STREAK:
                aborted = True
                print(
                    f"[ABORT] 連續 {rate_limit_streak} 次 rate_limit，"
                    f"於第 {idx}/{len(symbols)} 個 symbol 中止本次執行。"
                )
                break
        else:
            rate_limit_streak = 0

        if idx % 100 == 0 or idx == len(symbols):
            print(f"[{idx}/{len(symbols)}] saved={saved} skipped={skipped} fail={fail}")

        if reason != "skipped_exists":
            time.sleep(FETCH_INTERVAL_SECONDS)

    print("Done." if not aborted else "Aborted.")
    print(f"Saved: {saved}, Skipped: {skipped}, Failed: {fail}")
    for k in sorted(status_count):
        print(f"  {k}: {status_count[k]}")

    append_error_log(args.year, args.quarter, run_date, failures)

    return decide_exit_code(saved, fail, non_benign_fail, aborted)


if __name__ == "__main__":
    raise SystemExit(main())
