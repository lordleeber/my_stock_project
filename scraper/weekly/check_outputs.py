import datetime
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.error_log import append_error_log  # noqa: E402

ERROR_LOG = "error_scraper.log"

# TDCC OpenData 的檔名契約。只在這裡定義一次：之前 _extract_date 與 _check_freshness
# 各抄一份，兩份對同一個輸入的行為還不一致（前者回 ""、後者回 fail-closed tuple）。
TDCC_FILENAME_RE = re.compile(r"TDCC_OD_1-5_(\d{8})\.csv$")


def _snapshot_date(path: Path):
    """從檔名解析快照日期；解析不出來（含 8 碼但不是合法日期）時回傳 None。

    `20261332`、`99999999` 這類值過得了 `\\d{8}` 卻過不了 strptime。這裡把
    ValueError 收乾淨，呼叫端才能一致地走 fail-closed，而不是讓 checker 直接
    traceback——那等於連「有問題」都報不出來。
    """
    m = TDCC_FILENAME_RE.search(path.name)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def _append_missing(title, context, missing):
    if not missing:
        return
    lines = list(context) + ["Missing files:"] + [f"- {p}" for p in missing]
    append_error_log(ERROR_LOG, title, lines)


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

    # 解析不出日期的排在最前面，才不會蓋掉真正最新的那一份；真的只有壞檔時
    # 仍會被選中，並在 _check_freshness 走 fail-closed。
    candidates.sort(key=lambda p: (_snapshot_date(p) or datetime.date.min, p.name))
    return candidates[-1]


# TDCC 每週發布一份快照，基準日一律是週五；週五休市則順延到週四（實測 2025-08
# ~2026-08 的 52 份：45 份週五、7 份週四，且 2026-02-13 週五休市仍照發週五）。
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
    snap = _snapshot_date(latest_path)
    if snap is None:
        return False, f"cannot parse snapshot date from {latest_path.name}", None

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
            # 新鮮度只在 auto-detect 模式檢查。指定 TDCC_DATE 是「驗證硬碟上某
            # 一份既有快照」（重跑檢查、事後查核），此時舊日期是預期行為。
            # 注意 TDCC_DATE **不能**用來回補：OpenData endpoint 沒有日期參數，
            # 拿回來的永遠是最新一週；fetch_tdcc.py 現在會直接拒絕把最新資料寫成
            # 舊檔名。真的要補歷史請用 weekly/fetch_tdcc_history.py。
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
