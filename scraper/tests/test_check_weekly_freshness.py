"""scraper-weekly 的 TDCC 快照新鮮度檢查測試。

pytest 相容，但因為專案目前沒有安裝 pytest、CI 也沒跑（只跑 ruff），
本檔可以直接執行：

    venv/bin/python3 scraper/tests/test_check_weekly_freshness.py

這個 guard 的價值全在於「它會響」——若被改成永遠回 True 就完全失效，
而且失效方式是靜默的（跟它要防的 bug 一模一樣）。所以測試重點放在
**必須報錯的情境**，尤其是 2026-07-09 那次真實漏抓的重演。
"""

import contextlib
import datetime
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from common.error_log import append_error_log  # noqa: E402
from scraper.weekly.check_outputs import (  # noqa: E402
    FRESHNESS_WINDOW_DAYS,
    _check_freshness,
    _find_latest_tdcc_file,
    check_weekly_outputs,
)

# TDCC 2025-08 ~ 2026-08 的真實快照日期（取自歷史查詢頁的 scaDate 下拉選單）。
# 45 份週五、7 份週四（週五休市時順延），外加農曆年整週沒有快照。
REAL_SNAPSHOTS = [
    "20250808",
    "20250815",
    "20250822",
    "20250829",
    "20250905",
    "20250912",
    "20250919",
    "20250926",
    "20251003",
    "20251009",
    "20251017",
    "20251023",
    "20251031",
    "20251107",
    "20251114",
    "20251121",
    "20251128",
    "20251205",
    "20251212",
    "20251219",
    "20251226",
    "20260102",
    "20260109",
    "20260116",
    "20260123",
    "20260130",
    "20260206",
    "20260213",
    "20260226",
    "20260306",
    "20260313",
    "20260320",
    "20260327",
    "20260402",
    "20260410",
    "20260417",
    "20260424",
    "20260430",
    "20260508",
    "20260515",
    "20260522",
    "20260529",
    "20260605",
    "20260612",
    "20260618",
    "20260626",
    "20260703",
    "20260709",
    "20260717",
    "20260724",
    "20260731",
    "20260807",
]


@contextlib.contextmanager
def _cwd(path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _path(date_str):
    return Path(f"/x/{date_str[:4]}/TDCC_OD_1-5_{date_str}.csv")


def _date(iso):
    return datetime.date.fromisoformat(iso)


def _snapshot_date(date_str):
    """REAL_SNAPSHOTS 的 YYYYMMDD → date。"""
    return datetime.datetime.strptime(date_str, "%Y%m%d").date()


def test_replays_the_20260712_miss():
    """2026-07-12 的真實情境：7/10 週五休市 → 基準日改 7/09 → 當天沒抓到，
    硬碟上最新的還是 7/03。這一次必須報錯，否則 7/09 就永久消失。"""
    fresh, reason, snap = _check_freshness(_path("20260703"), _date("2026-07-12"))
    assert not fresh, "7/03 相對於 7/12 已經過期，必須判定為不新鮮"
    assert snap == _date("2026-07-03")
    assert "stale" in reason


def test_same_sunday_passes_when_the_snapshot_was_actually_fetched():
    """同一個週日，若正確抓到 7/09 就必須放行——否則會變成每週誤報。"""
    fresh, _, snap = _check_freshness(_path("20260709"), _date("2026-07-12"))
    assert fresh
    assert snap == _date("2026-07-09")


def test_weekday_mix_matches_the_documented_counts():
    """check_outputs.py 與 scraper/CLAUDE.md 都拿這組數字當「不預測週五/週四」的
    依據，所以直接從 REAL_SNAPSHOTS 算一次，免得註解與資料悄悄脫鉤。"""
    weekdays = [_snapshot_date(s).weekday() for s in REAL_SNAPSHOTS]
    fridays = weekdays.count(4)
    thursdays = weekdays.count(3)
    assert (len(REAL_SNAPSHOTS), fridays, thursdays) == (52, 45, 7), (
        f"實際為 {len(REAL_SNAPSHOTS)} 份 / {fridays} 週五 / {thursdays} 週四，"
        "與 check_outputs.py 及 scraper/CLAUDE.md 的註解不符"
    )
    assert fridays + thursdays == len(REAL_SNAPSHOTS), "出現週五/週四以外的基準日"


def test_thursday_snapshots_are_accepted():
    """週五休市時 TDCC 改發週四。檢查刻意不預測 TDCC 選哪天，只看新鮮度，
    所以每一份週四快照都必須通過。

    這裡從 REAL_SNAPSHOTS 現算而不是手抄清單：原本的手抄版漏了 2026-02-26 與
    2026-07-09，而 2026-07-09 正是這道 gate 要防的那次漏抓。
    """
    thursdays = [s for s in REAL_SNAPSHOTS if _snapshot_date(s).weekday() == 3]
    assert thursdays, "測試資料裡應該要有週四快照"
    for snap in thursdays:
        d = _snapshot_date(snap)
        sunday = d + datetime.timedelta(days=(6 - d.weekday()) % 7 or 7)
        fresh, reason, _ = _check_freshness(_path(snap), sunday)
        assert fresh, f"週四快照 {snap} 在 {sunday} 應被接受，卻回報：{reason}"


def test_every_real_sunday_passes_except_lunar_new_year():
    """把一整年的真實快照放回各自的週日重播：只有農曆年那週該報錯。

    2026-02-12~02-20 全週休市（daily_quotes 實測 2/11 之後直接跳到 2/23），
    TDCC 該週確實沒有快照，所以 2026-02-22 的告警是正確的，不是誤報。
    """
    snaps = sorted(_snapshot_date(s) for s in REAL_SNAPSHOTS)
    snapset = set(snaps)

    sunday = snaps[0]
    while sunday.weekday() != 6:
        sunday += datetime.timedelta(days=1)

    alerts = []
    checked = 0
    while sunday <= snaps[-1] + datetime.timedelta(days=2):
        window = [
            sunday - datetime.timedelta(days=k)
            for k in range(1, FRESHNESS_WINDOW_DAYS + 1)
        ]
        # 模擬「硬碟上最新的那一份」= 該週日之前最新的快照
        latest = max((d for d in snaps if d < sunday), default=None)
        if latest is not None:
            checked += 1
            fresh, _, _ = _check_freshness(_path(latest.strftime("%Y%m%d")), sunday)
            assert fresh == any(d in snapset for d in window), (
                f"{sunday} 的判定與 window 內是否有快照不一致"
            )
            if not fresh:
                alerts.append(sunday)
        sunday += datetime.timedelta(days=7)

    assert checked >= 50, f"重播的週日數過少（{checked}），測試資料可能有問題"
    assert alerts == [_date("2026-02-22")], (
        f"整年只該在農曆年那週告警一次，實際：{alerts}"
    )


def test_boundaries_are_inclusive():
    """window 是 [today-7, today-1] 閉區間。"""
    today = _date("2026-07-12")
    assert _check_freshness(_path("20260705"), today)[0], "today-7 應該通過"
    assert not _check_freshness(_path("20260704"), today)[0], "today-8 應該報錯"
    assert _check_freshness(_path("20260711"), today)[0], "today-1 應該通過"


def test_run_date_itself_and_future_are_rejected():
    """週日本身不會是 TDCC 基準日；未來日期代表檔名或系統時鐘有問題。"""
    today = _date("2026-07-12")
    for bad in ("20260712", "20260713"):
        fresh, reason, _ = _check_freshness(_path(bad), today)
        assert not fresh, f"{bad} 應該被拒絕"
        assert "future" in reason


def test_unparsable_filename_fails_closed():
    """解析不出日期時必須視為失敗，不能默默放行。"""
    fresh, reason, snap = _check_freshness(
        Path("/x/2026/garbage.csv"), _date("2026-07-12")
    )
    assert not fresh
    assert snap is None
    assert "cannot parse" in reason


def test_check_weekly_outputs_reports_stale_snapshot(tmp_path):
    """端到端：舊快照必須讓 check_weekly_outputs 回傳非空 missing，
    entrypoint 才會非零退出、systemd 的 OnFailure 才推得出通知。"""
    share = tmp_path / "raw" / "shareholding" / "2026"
    share.mkdir(parents=True)
    stale = share / "TDCC_OD_1-5_20260703.csv"
    stale.write_text("資料日期,證券代號\n20260703,2330\n", encoding="utf-8")

    # 容器外 _error_log_path() 會落在 CWD，chdir 進 tmp 以免在 repo 留下檔案
    with _cwd(tmp_path):
        missing = check_weekly_outputs(str(tmp_path))
    assert missing, "舊快照必須被回報為 missing，否則 weekly 會靜默通過"
    assert "stale" in missing[0]


def test_explicit_tdcc_date_skips_freshness(tmp_path):
    """指定 TDCC_DATE 是刻意鎖定某一天（回補、手動重跑），舊日期屬預期行為。"""
    share = tmp_path / "raw" / "shareholding" / "2026"
    share.mkdir(parents=True)
    old = share / "TDCC_OD_1-5_20260703.csv"
    old.write_text("資料日期,證券代號\n20260703,2330\n", encoding="utf-8")

    missing = check_weekly_outputs(str(tmp_path), tdcc_date="20260703")
    assert missing == [], f"指定日期模式不該做新鮮度檢查，卻回報：{missing}"


def test_impossible_date_fails_closed_instead_of_raising():
    """`99999999`、`20261332` 這種值過得了 \\d{8} 卻過不了 strptime。
    以前會直接拋 ValueError，checker 整支死掉——連「有問題」都報不出來。"""
    for bad in ("99999999", "20261332", "20260230"):
        fresh, reason, snap = _check_freshness(_path(bad), _date("2026-07-12"))
        assert not fresh, f"{bad} 必須 fail-closed"
        assert snap is None
        assert "cannot parse" in reason


def test_garbage_filename_does_not_hide_the_real_latest(tmp_path):
    """壞檔名排序時不能蓋掉真正最新的那一份（以前是純字串比大小，
    `TDCC_OD_1-5_99999999.csv` 會永遠排最後、每次都被選成 latest）。"""
    share = tmp_path / "2026"
    share.mkdir(parents=True)
    for name in ("TDCC_OD_1-5_99999999.csv", "TDCC_OD_1-5_20260807.csv"):
        (share / name).write_text("x", encoding="utf-8")

    latest = _find_latest_tdcc_file(tmp_path)
    assert latest.name == "TDCC_OD_1-5_20260807.csv", f"選到了 {latest}"


def test_only_garbage_still_reports_missing(tmp_path):
    """全部都是壞檔時仍必須回報問題，而不是 traceback 或靜默通過。"""
    share = tmp_path / "raw" / "shareholding" / "2026"
    share.mkdir(parents=True)
    bad = share / "TDCC_OD_1-5_99999999.csv"
    bad.write_text("資料日期,證券代號\n99999999,2330\n", encoding="utf-8")

    with _cwd(tmp_path):
        missing = check_weekly_outputs(str(tmp_path))
    assert missing, "壞檔名必須被回報，否則 weekly 會靜默通過"


def test_error_log_write_failure_does_not_crash(tmp_path):
    """error log 被 docker 建成目錄時（RESTORE.md §落差4），寫入必須 fail-soft：
    壞掉的是錯誤處理器，不該連帶讓呼叫端的判斷結果消失。"""
    (tmp_path / "error_scraper.log").mkdir()
    with _cwd(tmp_path):
        assert append_error_log("error_scraper.log", "t", ["line"]) is None


def test_gate_still_fires_when_the_error_log_is_a_directory(tmp_path):
    """端到端版本：log 寫不進去，missing 仍必須照常回報（否則 gate 天生失效）。"""
    share = tmp_path / "raw" / "shareholding" / "2026"
    share.mkdir(parents=True)
    (share / "TDCC_OD_1-5_20260703.csv").write_text(
        "資料日期,證券代號\n20260703,2330\n", encoding="utf-8"
    )
    (tmp_path / "error_scraper.log").mkdir()

    with _cwd(tmp_path):
        missing = check_weekly_outputs(str(tmp_path))
    assert missing, "log 寫入失敗不能吃掉 missing"


def _run_standalone() -> int:
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                    fn(Path(td))
                else:
                    fn()
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
            else:
                print(f"ok   {name}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
