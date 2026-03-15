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


def detect_blocked_reason(html_text: str) -> str | None:
    lower = html_text.lower()
    marker_reason_pairs = [
        ("overrun - 查詢過於頻繁", "rate_limit"),
        ("查詢過於頻繁,請稍後再試", "rate_limit"),
        ("too many query requests from your ip", "rate_limit"),
        ("the page can not be accessed", "page_not_accessible"),
        ("頁面無法執行", "page_not_accessible"),
    ]
    for marker, reason in marker_reason_pairs:
        if marker.lower() in lower:
            return reason
    return None


def strip_run_date_suffix(filename: str) -> str:
    # Convert YYYYQX_1234_YYYYMMDD.html -> YYYYQX_1234.html
    return re.sub(r"_\d{8}(?=\.html$)", "", filename)


def load_existing_report_names(out_dir: Path) -> set[str]:
    names: set[str] = set()
    for path in out_dir.glob("*.html"):
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
            if "<html" not in html_text.lower():
                last_status = "invalid_html"
                print(f"[FAIL] {symbol} -> {last_status}")
            else:
                blocked_reason = detect_blocked_reason(html_text)
                if blocked_reason:
                    last_status = f"blocked_page:{blocked_reason}"
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
