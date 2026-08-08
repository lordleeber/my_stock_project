import datetime
import os
import re
from pathlib import Path


def _error_log_path() -> Path:
    # 與 quarterly/fetch_xbrl.py::get_error_log_path 同一個 pattern：容器內走
    # /app（compose 有 bind mount 出來），容器外（測試、手動執行）落在 CWD，
    # 免得因為 /app 不存在直接 FileNotFoundError。
    app_log = Path("/app/error_scraper.log")
    return app_log if app_log.parent.exists() else Path("error_scraper.log")


def _append_missing(title, context, missing):
    if not missing:
        return
    error_md = _error_log_path()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_md, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] {title}\n")
        for line in context:
            f.write(f"{line}\n")
        f.write("Missing files:\n")
        for path in missing:
            f.write(f"- {path}\n")
    print(f"\n[WARN] Missing outputs detected. See: {error_md}")


def _is_file_valid(path: Path, min_bytes: int, min_lines: int) -> bool:
    if not path.exists():
        return False
    try:
        if path.stat().st_size < min_bytes:
            return False
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            line_count = 0
            for _ in f:
                line_count += 1
                if line_count >= min_lines:
                    return True
        return False
    except OSError:
        return False


def _find_latest_tdcc_file(base_dir: Path):
    candidates = list(base_dir.glob("*/TDCC_OD_1-5_*.csv"))
    if not candidates:
        return None

    def _extract_date(path: Path):
        m = re.search(r"TDCC_OD_1-5_(\d{8})\.csv$", path.name)
        return m.group(1) if m else ""

    candidates.sort(key=lambda p: _extract_date(p))
    return candidates[-1]


# TDCC 每週發布一份快照，基準日一律是週五；週五休市則順延到週四（實測 2025-08
# ~2026-08 的 52 份：47 份週五、5 份週四，且 2026-02-13 週五休市仍照發週五）。
# 我們每週日 10:20 跑，所以「這次該拿到的那一份」必然落在 [today-7, today-1]：
# 往前推 7 天一定涵蓋到剛過去的那個週四/週五，而今天（週日）本身不會是基準日。
#
# 這個檢查刻意不去預測 TDCC 會選週五還是週四，只斷言新鮮度 —— 因此不需要維護
# 交易日曆，也不會因為 TDCC 改變選日規則而失效。
#
# 為什麼需要它：fetch_tdcc.py 打的 OpenData endpoint 沒有日期參數，永遠只回
# 「最新一週」。TDCC 延遲發布時這支會抓回上週那份、覆寫同名舊檔，而原本的檢查
# 只看「最新檔存在且 >10 bytes」，於是整條 pipeline 靜默通過，該週就永久缺漏。
# 2026-07-09 那份就是這樣掉的（7/10 週五休市 → 基準日改週四 → 7/12 沒抓到 →
# 7/19 抓到的已是 7/17）。TDCC OpenData 不提供歷史，補救只能逐檔爬歷史查詢頁。
FRESHNESS_WINDOW_DAYS = 7


def _check_freshness(latest_path: Path, today: datetime.date):
    """回傳 (是否新鮮, 說明字串, 快照日期)。無法解析檔名日期時視為不新鮮（fail-closed）。"""
    m = re.search(r"TDCC_OD_1-5_(\d{8})\.csv$", latest_path.name)
    if not m:
        return False, f"cannot parse snapshot date from {latest_path.name}", None

    snap = datetime.datetime.strptime(m.group(1), "%Y%m%d").date()
    oldest_ok = today - datetime.timedelta(days=FRESHNESS_WINDOW_DAYS)
    newest_ok = today - datetime.timedelta(days=1)

    if snap < oldest_ok:
        return (
            False,
            f"snapshot {snap:%Y-%m-%d} is stale: expected one dated "
            f"{oldest_ok:%Y-%m-%d}..{newest_ok:%Y-%m-%d} (run date {today:%Y-%m-%d})",
            snap,
        )
    if snap > newest_ok:
        return (
            False,
            f"snapshot {snap:%Y-%m-%d} is in the future relative to run date "
            f"{today:%Y-%m-%d} (expected {oldest_ok:%Y-%m-%d}..{newest_ok:%Y-%m-%d})",
            snap,
        )
    return (
        True,
        f"snapshot {snap:%Y-%m-%d} within {oldest_ok:%Y-%m-%d}..{newest_ok:%Y-%m-%d}",
        snap,
    )


def check_weekly_outputs(output_dir, tdcc_date=""):
    base_dir = Path(output_dir).resolve() / "raw" / "shareholding"
    min_bytes = int(os.getenv("MIN_BYTES", "10"))
    min_lines = int(os.getenv("MIN_LINES", "2"))

    missing = []
    context = []

    if tdcc_date:
        year = tdcc_date[:4]
        target = base_dir / year / f"TDCC_OD_1-5_{tdcc_date}.csv"
        context.append(f"Date: {tdcc_date}")
        if not _is_file_valid(target, min_bytes, min_lines):
            missing.append(str(target))
    else:
        latest = _find_latest_tdcc_file(base_dir)
        context.append("Date: auto-detect latest")
        if latest is None:
            missing.append(str(base_dir / "<year>/TDCC_OD_1-5_YYYYMMDD.csv"))
        elif not _is_file_valid(latest, min_bytes, min_lines):
            missing.append(str(latest))
        else:
            context.append(f"Latest file: {latest}")
            # 新鮮度只在 auto-detect 模式檢查。指定 TDCC_DATE 時是刻意鎖定某一天
            # （回補、手動重跑），此時舊日期是預期行為，不該告警。
            fresh, reason, _snap = _check_freshness(latest, datetime.date.today())
            context.append(f"Freshness: {reason}")
            if not fresh:
                if os.getenv("ALLOW_STALE_TDCC", "0") == "1":
                    print(
                        f"[WARN] Stale TDCC snapshot allowed by ALLOW_STALE_TDCC=1: {reason}"
                    )
                else:
                    missing.append(
                        f"{base_dir}/<year>/TDCC_OD_1-5_YYYYMMDD.csv — {reason}"
                    )

    _append_missing(
        title="scraper-weekly missing outputs",
        context=context,
        missing=missing,
    )
    return missing


def main():
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    tdcc_date = os.getenv("TDCC_DATE", "").strip()

    if tdcc_date and (len(tdcc_date) != 8 or not tdcc_date.isdigit()):
        print(f"[WARN] Invalid TDCC_DATE: {tdcc_date}. Fallback to latest file check.")
        tdcc_date = ""

    missing = check_weekly_outputs(output_dir, tdcc_date)
    if missing:
        print(f"[FAIL] {len(missing)} weekly output problem(s) detected.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
