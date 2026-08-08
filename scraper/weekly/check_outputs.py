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


def _write_report(context, problems, waived):
    """把這次檢查的結果寫進 error log。

    `waived` 即使沒有 problems 也要寫：ALLOW_STALE_TDCC=1 是一次刻意的放行，
    如果只印到 stdout，紀錄就隨 container `--rm` 消失了——幾個月後回頭查籌碼
    缺口時，這份「本來就是要拿來查」的 log 反而看不出那週是被人知情跳過的。

    每一筆都以**真實路徑**開頭，後面才接原因。之前把 `<year>/TDCC_OD_1-5_
    YYYYMMDD.csv` 這種佔位字串混在真實路徑裡，任何拿 log 去撈路徑重抓的工具
    都會拿到一個不存在的檔名。
    """
    if not problems and not waived:
        return
    lines = list(context)
    if waived:
        lines.append("Waived by ALLOW_STALE_TDCC=1:")
        lines += [f"- {w}" for w in waived]
    if problems:
        lines.append("Problems:")
        lines += [f"- {p}" for p in problems]
    title = (
        "scraper-weekly output problems"
        if problems
        else "scraper-weekly stale snapshot waived"
    )
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


def _snapshot_dates(base_dir: Path, today: datetime.date):
    """回傳硬碟上所有可解析的快照日期（去重、由舊到新）。

    未來日期一併排除：那是壞檔（已由 _find_latest_tdcc_file 單獨回報），留著只會
    在連續性檢查裡製造一個橫跨數十年的假缺口，把真正的問題淹掉。
    """
    dates = {
        d
        for d in (_snapshot_date(p) for p in base_dir.glob("*/TDCC_OD_1-5_*.csv"))
        if d is not None and d <= today
    }
    return sorted(dates)


def _find_latest_tdcc_file(base_dir: Path, today: datetime.date):
    """挑出「最新但不晚於 today」的那一份。

    只取 max 會被單一個未來日期的檔案永久卡住：`TDCC_OD_1-5_20990709.csv`
    （手動 cp 錯、或早期版本的 TDCC_DATE 打錯字留下的）會每次都被選成 latest，
    於是 _check_freshness 永遠回報 in the future，就算正確的當週快照已經抓回來
    也一樣失敗。所以未來日期的檔案排除在候選之外，另外單獨回報。
    """
    candidates = list(base_dir.glob("*/TDCC_OD_1-5_*.csv"))
    if not candidates:
        return None, []

    future = sorted(
        p for p in candidates if (_snapshot_date(p) or datetime.date.min) > today
    )
    usable = [p for p in candidates if p not in set(future)]
    if not usable:
        # 全部都在未來（或全是壞檔名）時仍要回傳一份，讓 _check_freshness 走
        # fail-closed 把原因寫清楚，而不是回 None 變成「一個檔案都沒有」。
        usable = candidates

    # 解析不出日期的排在最前面，才不會蓋掉真正最新的那一份。
    usable.sort(key=lambda p: (_snapshot_date(p) or datetime.date.min, p.name))
    return usable[-1], future


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

# 新鮮度只看「最新那一份」，所以它有一個結構性盲點：**缺口一旦被下一週的快照蓋過
# 去就永遠看不見了**。重演 2026-07-12 那次——當天 gate 會響，但如果通知被錯過、
# 或 timer 根本沒觸發（unit 掛掉、機器關機），到了 7/19 硬碟上最新的是 7/17，
# 落在 [7/12, 7/18] 之內 → fresh=True → 那一週就這樣安靜地永久消失。
#
# 所以另外驗一次「連續性」：相鄰兩份快照的間隔不得超過 MAX_SNAPSHOT_GAP_DAYS。
# 實測 2025-08~2026-08 的 52 份，間隔分布是 6 天 ×6、7 天 ×37、8 天 ×7、13 天 ×1
# （13 天那次是農曆年整週休市）。漏掉一週會變成 14 天。取 9 天：正常週完全不會誤
# 報，漏一週必中，而農曆年那次落在 13 天也會響一次——與新鮮度 gate 的告警頻率一致
# （一年一次），同樣用 ALLOW_STALE_TDCC=1 放行。
MAX_SNAPSHOT_GAP_DAYS = 9

# 只回頭看這麼多天。這個檢查的用途是「讓被錯過的那次告警再有幾次機會」，不是把
# 歷史上所有缺口都清點一遍——TDCC OpenData 沒有歷史，舊缺口本來就補不回來，每週
# 重報只會變成長期雜訊，最後大家學會忽略它（那就跟沒有 gate 一樣了）。
# 取 30 天 ≈ 4 個週日：漏抓當週的新鮮度 gate 會先響一次，之後連續性再響約 4 次，
# 然後安靜下來。
CONTINUITY_LOOKBACK_DAYS = 30


def _check_continuity(snapshots, today: datetime.date):
    """回傳最近 CONTINUITY_LOOKBACK_DAYS 內間隔過大的 (前一份, 後一份) 清單。

    窗口兩端都要夾：只夾下界的話，重播歷史（或硬碟上存在未來日期的檔案）時會把
    今天之後的快照也算進來，於是任何一個歷史缺口從一開始就週週都響。
    """
    since = today - datetime.timedelta(days=CONTINUITY_LOOKBACK_DAYS)
    recent = [d for d in snapshots if since <= d <= today]
    return [
        (a, b)
        for a, b in zip(recent, recent[1:])
        if (b - a).days > MAX_SNAPSHOT_GAP_DAYS
    ]


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


def check_weekly_outputs(output_dir, tdcc_date="", today=None):
    base_dir = Path(output_dir).resolve() / "raw" / "shareholding"
    min_bytes = int(os.getenv("MIN_BYTES", "10"))
    min_lines = int(os.getenv("MIN_LINES", "2"))
    today = today or datetime.date.today()
    allow_stale = os.getenv("ALLOW_STALE_TDCC", "0") == "1"

    problems = []
    waived = []
    context = []

    if tdcc_date:
        year = tdcc_date[:4]
        target = base_dir / year / f"TDCC_OD_1-5_{tdcc_date}.csv"
        context.append(f"Date: {tdcc_date}")
        if not _is_file_valid(target, min_bytes, min_lines):
            problems.append(f"{target} — missing or invalid")
        _write_report(context, problems, waived)
        return problems

    context.append("Date: auto-detect latest")
    latest, future = _find_latest_tdcc_file(base_dir, today)

    # 未來日期的檔案要指名道姓：操作者必須知道該刪哪一個，訊息裡給檔名 pattern
    # 是沒用的。
    for p in future:
        problems.append(f"{p} — snapshot date is in the future (run date {today})")

    if latest is None:
        problems.append(f"{base_dir} — no TDCC snapshot found")
        _write_report(context, problems, waived)
        return problems

    if not _is_file_valid(latest, min_bytes, min_lines):
        problems.append(f"{latest} — missing or invalid")
        _write_report(context, problems, waived)
        return problems

    context.append(f"Latest file: {latest}")

    # 新鮮度只在 auto-detect 模式檢查。指定 TDCC_DATE 是「驗證硬碟上某一份既有
    # 快照」（重跑檢查、事後查核），此時舊日期是預期行為。
    # 注意 TDCC_DATE **不能**用來回補：OpenData endpoint 沒有日期參數，拿回來的
    # 永遠是最新一週；fetch_tdcc.py 現在會直接拒絕把最新資料寫成舊檔名。
    # 真的要補歷史請用 weekly/fetch_tdcc_history.py。
    fresh, reason, _snap = _check_freshness(latest, today)
    context.append(f"Freshness: {reason}")
    if not fresh:
        if allow_stale:
            waived.append(f"{latest} — {reason}")
            print(f"[WARN] Stale TDCC snapshot allowed by ALLOW_STALE_TDCC=1: {reason}")
        else:
            problems.append(f"{latest} — {reason}")

    # 連續性：補上新鮮度看不見的那個盲點（缺口被下一週蓋過去之後就無感了）。
    gaps = _check_continuity(_snapshot_dates(base_dir, today), today)
    context.append(f"Continuity: {len(gaps)} gap(s) > {MAX_SNAPSHOT_GAP_DAYS}d")
    for a, b in gaps:
        detail = (
            f"{base_dir} — missing snapshot(s) between {a:%Y-%m-%d} and "
            f"{b:%Y-%m-%d} ({(b - a).days}d gap; TDCC OpenData 無歷史，"
            f"回補請用 weekly/fetch_tdcc_history.py)"
        )
        if allow_stale:
            waived.append(detail)
        else:
            problems.append(detail)

    _write_report(context, problems, waived)
    return problems


def normalize_tdcc_date(raw):
    """把 TDCC_DATE 正規化成 YYYYMMDD，格式不對就回 ""（並印出警告）。

    兩個 entrypoint（scraper_weekly.py 與這裡的 main()）都必須走這一條，否則
    像 `2026-07-09` 這種很自然的打錯（repo 其他 CLI 一律用 --date YYYY-MM-DD）
    會在兩邊得到不同結果。
    """
    raw = (raw or "").strip()
    if raw and (len(raw) != 8 or not raw.isdigit()):
        print(f"[WARN] Invalid TDCC_DATE: {raw}. Fallback to latest file check.")
        return ""
    return raw


def fail_if_problems(problems, label="weekly"):
    """checker 回報問題就讓 entrypoint 非零退出（與 scraper_daily.py 同慣例），
    weekly_update.sh 的 set -e 才會中斷，systemd 的 OnFailure 才推得出通知。"""
    if problems:
        print(f"[FAIL] {len(problems)} {label} output problem(s) detected.")
        return 1
    return 0


def main():
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    tdcc_date = normalize_tdcc_date(os.getenv("TDCC_DATE"))
    return fail_if_problems(check_weekly_outputs(output_dir, tdcc_date))


if __name__ == "__main__":
    raise SystemExit(main())
