"""Unit tests for strategies.step2_finalize_strategy.assert_features_not_beyond_cutoff.

這道 guard 是 look-ahead 的回歸防護：step2 把 fetch_* 實際撈回的稽核欄
（tech_snapshot_date / rev_max_publish_time）交給它，任何一筆越過 cutoff 就 raise。

**為什麼一定要有單元測試**：guard 本身在 live run 抓不到「as-of 被改回 entry_date」
——那一刻 DB 根本還沒有 entry_date 的列，fetch 會自動退回 cutoff，沒有東西可驗。
它要到第一次歷史重跑才引爆，而那時訓練集已經被汙染過一輪了。這支測試是唯一能在
commit 當下就攔下來的機制，所以它補的不是覆蓋率，是防護鏈缺的那一環。

鎖死的合約：

  - 純函式：不收 engine、不發查詢。斷言的輸入必須是「撈回來的資料本身」，
    改成獨立 DB 查詢正是上一版 guard 變成空殼的原因（見 PR #19 / #20）
  - 技術快照越過 cutoff  → raise（as-of 被改回 entry_date 的主要症狀）
  - 營收 publish_time 越過 cutoff → raise（同一個回歸的營收側；月份層級驗不出來，
    publish_time 才是判別式）
  - 快照落後／超前 step1 的最新 quote_date → 分別 raise，且訊息要指向不同的修法
    （補跑 calculator vs 重跑 step1）
  - quote_date 是 per-symbol 的，停牌股會讓集合變多值：比對必須是等值而非集合成員
  - 兩個稽核欄「驗不了」一律 fail-closed，不可靜默放行

執行（venv 未裝 pytest 也能跑）：
  venv/bin/python3 strategies/tests/test_feature_asof_guard.py          # 內建 runner
  venv/bin/python3 -m pytest strategies/tests/test_feature_asof_guard.py  # 若有 pytest
"""

import inspect
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# 將專案根目錄加入路徑（與 processor/tests/test_quarterly_logic.py 同慣例）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from strategies.feature_engineering import (  # noqa: E402
    REVENUE_FEATURE_COLS,
    TECHNICAL_FEATURE_COLS,
    fetch_revenue_features,
    fetch_technical_features,
)
from strategies.step2_finalize_strategy import (  # noqa: E402
    assert_features_not_beyond_cutoff,
)

CUTOFF = "2026-07-10"  # 2026-07 颱風那次的 cutoff（PR #19 的實測案例）
QUOTE = "2026-07-09"  # cutoff 當天無交易 → step1 退回前一交易日
ENTRY = "2026-07-13"  # 回歸發生時 as-of 會跑到這天


def _tech(snapshot_dates):
    """造一個最小 fetch_technical_features 回傳值：只有 assert 會讀的稽核欄。

    真實回傳還有 TECHNICAL_FEATURE_COLS，但 assert 不看它們——刻意不造，
    以免測試對無關欄位過度耦合。
    """
    dates = snapshot_dates if isinstance(snapshot_dates, list) else [snapshot_dates]
    return pd.DataFrame(
        {
            "symbol": [f"{1101 + i}" for i in range(len(dates))],
            "tech_snapshot_date": dates,
        }
    )


def _rev(publish_times):
    """同上，fetch_revenue_features 的最小回傳值（publish_time 為 YYYYMMDD str）。"""
    times = publish_times if isinstance(publish_times, list) else [publish_times]
    return pd.DataFrame(
        {
            "symbol": [f"{1101 + i}" for i in range(len(times))],
            "rev_max_publish_time": times,
        }
    )


def _assert_raises(fn, *needles):
    """執行 fn，要求 raise SystemExit，且訊息含所有 needles。回傳訊息。"""
    try:
        fn()
    except SystemExit as exc:
        msg = str(exc)
        for needle in needles:
            assert needle in msg, f"訊息缺少 {needle!r}：{msg}"
        return msg
    raise AssertionError(f"expected SystemExit containing {needles}")


# ── 合約：純函式，不得回頭發查詢 ──────────────────────────────────────────────


def test_signature_takes_frames_not_engine():
    """斷言的輸入必須是 fetch 回傳的 frame，不是 engine。

    上一版 guard 比對的兩個值都繞過了 fetch_*（一個獨立的 MAX(date) 查詢 vs step1
    的 quote_date），所以把 as-of 改回 entry_date 兩邊都不動、檢查照過。收 engine
    就是滑回那個設計的第一步，這裡把它鎖死。
    """
    params = list(inspect.signature(assert_features_not_beyond_cutoff).parameters)
    assert params == ["tech", "rev", "quote_dates", "cutoff_date"]
    assert "engine" not in params


def test_fetch_functions_emit_the_audit_columns():
    """fetch_* 的空輸入分支必須帶稽核欄——step2 直接 drop 它，缺欄會 KeyError。

    走 symbols=[] 分支，不碰 DB。
    """
    tech_cols = list(fetch_technical_features([], CUTOFF).columns)
    assert tech_cols == ["symbol", "tech_snapshot_date"] + TECHNICAL_FEATURE_COLS

    rev_cols = list(fetch_revenue_features([], CUTOFF).columns)
    assert rev_cols == ["symbol", "rev_max_publish_time"] + REVENUE_FEATURE_COLS


# ── 正常路徑 ──────────────────────────────────────────────────────────────────


def test_correct_asof_passes():
    """as-of = cutoff：快照 == 最新 quote_date、publish_time <= cutoff → 放行。"""
    assert_features_not_beyond_cutoff(
        _tech(QUOTE), _rev("20260710"), {QUOTE}, CUTOFF
    )  # 不 raise 即通過


def test_suspended_symbol_older_quote_date_still_passes():
    """停牌股讓 quote_dates 變多值，但 max 對得上快照 → 仍應放行（不可誤報）。"""
    assert_features_not_beyond_cutoff(
        _tech([QUOTE, "2026-06-15"]),
        _rev(["20260710", "20260610"]),
        {QUOTE, "2026-06-15"},
        CUTOFF,
    )


# ── 回歸：as-of 被改回 entry_date ─────────────────────────────────────────────


def test_tech_snapshot_beyond_cutoff_raises():
    """PR #19 的主症狀：技術快照跑到 entry_date（cutoff 之後）。"""
    msg = _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech(ENTRY), _rev("20260710"), {QUOTE}, CUTOFF
        ),
        "越過 cutoff",
        ENTRY,
    )
    assert "entry_date" in msg  # 訊息要指出真正的成因


def test_revenue_publish_time_beyond_cutoff_raises():
    """同一個回歸的營收側：2026M06 有 192 筆申報落在 cutoff 之後。

    月份層級驗不出來（expected_revenue_month(cutoff) == expected_revenue_month(entry)），
    publish_time 才是判別式——這正是本欄存在的理由。
    """
    _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech(QUOTE), _rev("20260713"), {QUOTE}, CUTOFF
        ),
        "營收 publish_time",
        "20260713",
    )


def test_revenue_check_is_independent_of_tech_check():
    """只有營收側被改回 entry_date 時也要抓到（技術側正常不能掩護它）。"""
    _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech(QUOTE), _rev(["20260710", "20260713"]), {QUOTE}, CUTOFF
        ),
        "營收 publish_time",
    )


# ── step1／step2 之間 DB 漂移：兩個方向要分開講 ────────────────────────────────


def test_tech_lagging_quote_date_raises_with_calculator_hint():
    """快照落後 quote_date = technical_indicators 沒跟上 daily_quotes。

    成因是 calculator 沒跑完，重跑 step1 只會拿到同一個 quote_date、修不好，
    所以訊息不可以叫人重跑 step1。
    """
    msg = _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech("2026-07-08"), _rev("20260710"), {QUOTE}, CUTOFF
        ),
        "落後",
        "calculator",
    )
    assert "重跑 step1 不會改變" in msg


def test_tech_leading_quote_date_raises_with_step1_hint():
    """快照超前 quote_date（但仍 <= cutoff）= step1 產出後 DB 又匯入新資料。"""
    _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech(CUTOFF), _rev("20260710"), {"2026-07-09"}, CUTOFF
        ),
        "超前",
        "重跑 step1",
    )


def test_stale_tech_not_masked_by_suspended_symbol_quote_date():
    """等值比對而非集合成員：這是 `in` 判定會漏掉的情境。

    calculator 整批沒跑，全宇宙技術指標停在 2026-06-15；集合裡剛好有一檔停牌股的
    quote_date 也是 2026-06-15 → `tech_max in quote_dates` 會通過，整批特徵過期
    20 天無人知曉。等值比對對上的是 max(quote_dates)，所以會 raise。
    """
    _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech("2026-06-15"),
            _rev("20260710"),
            {QUOTE, "2026-06-15"},  # 2026-07-09 才是市場最新交易日
            CUTOFF,
        ),
        "落後",
        "2026-06-15",
    )


# ── fail-closed：驗不了等同失敗 ───────────────────────────────────────────────


def test_all_nan_revenue_audit_column_raises():
    """營收稽核欄全空必須 raise，不可印著 `rev_publish<=nan ✓` 放行。

    今天走不到（fetch_revenue_features 在零資料時先 raise 了），但 guard 的價值在於
    撐過未來的重構——「檢查安靜地變成空的」正是 #19 那版 guard 的死法。
    """
    _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech(QUOTE), _rev([np.nan]), {QUOTE}, CUTOFF
        ),
        "無法驗證營收 as-of",
    )


def test_empty_tech_frame_raises():
    """技術稽核欄全空同樣 fail-closed。"""
    _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            pd.DataFrame(columns=["symbol", "tech_snapshot_date"]),
            _rev("20260710"),
            {QUOTE},
            CUTOFF,
        ),
        "無法驗證特徵 as-of",
    )


def test_empty_quote_dates_raises():
    """step1 的 quote_date 全空時無從比對，也要 fail-closed。"""
    _assert_raises(
        lambda: assert_features_not_beyond_cutoff(
            _tech(QUOTE), _rev("20260710"), set(), CUTOFF
        ),
        "無法驗證特徵 as-of",
    )


def _run_all():
    """venv 未裝 pytest 時的內建 runner：跑完所有 test_* 並回報。"""
    tests = sorted(
        (name, fn)
        for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - test runner needs the catch-all
            failures.append((name, exc))
            print(f"FAIL  {name}: {exc!r}")
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
