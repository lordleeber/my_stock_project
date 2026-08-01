import argparse
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode


BASE_URL = "https://mopsov.twse.com.tw/server-java/t164sb01"
ACTIVE_STOCKS_FILE = Path("active_stocks.txt")
OUTPUT_ROOT = Path("data/raw/xbrl")
MAX_RETRIES = 0

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


def get_error_log_path() -> Path:
    app_log = Path("/app/error_scraper.log")
    return app_log if app_log.parent.exists() else Path("error_scraper.log")


def append_error_log(
    year: int, quarter: int, run_date: str, failures: list[tuple[str, str]]
):
    if not failures:
        return
    error_log = get_error_log_path()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with error_log.open("a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] scraper-quarterly-detail-xbrl failures\n")
        f.write(f"Quarter: {year}Q{quarter}\n")
        f.write(f"run_date: {run_date}\n")
        f.write(f"failed_count: {len(failures)}\n")
        for symbol, status in failures:
            f.write(f"- {symbol}: {status}\n")
    print(f"\n[WARN] Failures written to: {error_log}")


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


def fetch_xbrl_html(symbol: str, year: int, quarter: int, timeout: int = 30) -> bytes:
    params = {
        "step": 1,
        "CO_ID": symbol,
        "SYEAR": year,
        "SSEASON": quarter,
        "REPORT_ID": "C",
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


def strip_run_date_suffix(filename: str) -> str:
    # Convert YYYYQX_1234_YYYYMMDD.html -> YYYYQX_1234.html
    return re.sub(r"_\d{8}(?=\.html$)", "", filename)


def is_valid_report_file(path: Path) -> bool:
    """既有檔案看起來是不是一份正常季報（大小 + 檔頭的 XBRL marker）。

    只讀檔頭：整季約 1,600 份、每份約 500 KB，全讀進來只為了 dedupe 太浪費。
    """
    try:
        if path.stat().st_size < MIN_REPORT_BYTES:
            return False
        with path.open("rb") as f:
            head = f.read(HEAD_SCAN_BYTES).lower()
    except OSError:
        return False
    return any(marker.lower().encode("utf-8") in head for marker in XBRL_MARKERS)


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


def save_symbol_report(
    symbol: str,
    year: int,
    quarter: int,
    run_date: str,
    out_dir: Path,
    existing_report_names: set[str],
    force: bool = False,
) -> tuple[str, str]:
    base_filename = f"{year}Q{quarter}_{symbol}.html"
    filename = f"{year}Q{quarter}_{symbol}_{run_date}.html"
    out_path = out_dir / filename
    if not force and base_filename in existing_report_names:
        print(f"[SKIP] {symbol} -> skipped_exists ({base_filename})")
        return symbol, "skipped_exists"

    attempts = MAX_RETRIES + 1
    last_status = "error:unknown"
    for attempt in range(1, attempts + 1):
        try:
            print(f"[FETCH] {symbol} (attempt {attempt}/{attempts})")
            raw_html = fetch_xbrl_html(symbol, year, quarter)
            html_text = decode_to_utf8(raw_html)
            invalid_reason = validate_report(html_text)
            if invalid_reason:
                # 能認出是哪種 MOPS 回應就用它（report_not_published 只是還沒申報，
                # 不是故障），認不出來才退回 validate_report 的結構性原因。
                last_status = (
                    classify_failure_reason(html_text)
                    or f"invalid_report:{invalid_reason}"
                )
                print(f"[FAIL] {symbol} -> {last_status}")
            else:
                out_path.write_text(html_text, encoding="utf-8")
                existing_report_names.add(base_filename)
                return symbol, "ok"
        except Exception as e:
            last_status = f"error:{e}"
            print(f"[FAIL] {symbol} -> {last_status}")

            if attempt < attempts:
                time.sleep(0.3 * attempt)

    return symbol, f"{last_status};retries={MAX_RETRIES}"


def main():
    parser = argparse.ArgumentParser(
        description="Fetch detailed quarterly XBRL HTML reports from MOPS."
    )
    parser.add_argument("--year", type=int, required=True, help="AD year, e.g. 2025")
    parser.add_argument(
        "--quarter", type=int, required=True, choices=[1, 2, 3, 4], help="Quarter 1~4"
    )
    args = parser.parse_args()
    force_reprocess = os.getenv("FORCE_REPROCESS", "0") == "1"

    symbols = load_symbols(ACTIVE_STOCKS_FILE)
    if not symbols:
        print("No valid symbols found in active_stocks.txt")
        return 1

    run_date = datetime.now().strftime("%Y%m%d")
    quarter_key = f"{args.year}Q{args.quarter}"
    out_dir = OUTPUT_ROOT / str(args.year) / quarter_key
    out_dir.mkdir(parents=True, exist_ok=True)
    existing_report_names = load_existing_report_names(out_dir)

    print(f"Target quarter: {quarter_key}")
    print(f"Symbols: {len(symbols)}")
    print(f"Output: {out_dir}")
    print(f"run_date: {run_date}")
    print(f"existing_reports: {len(existing_report_names)}")
    print(
        f"overwrite: {'enabled' if force_reprocess else 'disabled'} (FORCE_REPROCESS)"
    )

    ok = 0
    fail = 0
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
        )
        status_count[status] = status_count.get(status, 0) + 1
        if status in {"ok", "skipped_exists"}:
            ok += 1
        else:
            fail += 1
            failures.append((symbol, status))

        if idx % 100 == 0 or idx == len(symbols):
            print(f"[{idx}/{len(symbols)}] ok={ok} fail={fail}")

        if status != "skipped_exists":
            time.sleep(3)

    print("Done.")
    print(f"Saved: {ok}, Failed: {fail}")
    for k in sorted(status_count):
        print(f"  {k}: {status_count[k]}")

    append_error_log(args.year, args.quarter, run_date, failures)
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
