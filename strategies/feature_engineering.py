"""
選股模型的共用特徵工程模組。

依指定基準日，從 technical_indicators 撈取預計算的技術指標，
並從 monthly_revenue 撈取月營收特徵。

⚠️ **本模組所有 `as_of_date` 參數一律傳 `cutoff_date`，不可傳 `entry_date`。**
每支函式的語意都是「取 <= as_of_date 的最新一筆」。傳 entry_date 在正式執行時
看似無害（那天還沒到、DB 沒資料，自動退回 cutoff），但那個 PIT 保證來自牆上
時鐘而非程式碼：歷史重跑時 DB 早已涵蓋 entry_date，同一段程式就會取到決策當下
拿不到的資料。詳見 strategies/CLAUDE.md「Feature as-of is cutoff_date」。
新增函式請沿用這個契約。

被以下腳本使用：
  - step2_finalize_strategy.py  （fetch_* 特徵撈取，唯一的 fetch 呼叫端）
  - step3_analyze_feature_returns.py / step4_train_selection_model.py
    （只 import TECHNICAL_FEATURE_COLS / REVENUE_FEATURE_COLS 欄位常數）

本模組不留沒有呼叫端的 fetch_*：這裡每支 fetch 都收 as_of_date，而 as-of 的防護
（step2 的 assert_features_not_beyond_cutoff）只驗 step2 實際撈回的稽核欄，所以一支
沒人叫的 fetch 等於一條沒有護欄的旁路，哪天被接上去就直接繞過檢查。
fetch_institutional_flow_features / fetch_price_features 在 strategies_benchmark/
（0d16ec9 移除）之後就沒有呼叫端，已一併刪除；需要時從 git 取回並補上稽核欄。
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import bindparam, create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url


# 從 technical_indicators 撈取的原始欄位。
_TI_COLS = [
    "ma5",
    "ma10",
    "ma20",
    "ma60",
    "ma240",
    "vma5",
    "vma10",
    "vma20",
    "k",
    "d",
    "rsi6",
    "rsi12",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "foreign_streak_days",
    "trust_streak_days",
    "dealer_streak_days",
]

# 由原始技術指標值與收盤價計算出的比值特徵，這些才是實際進入模型的欄位。
TECHNICAL_FEATURE_COLS = [
    "close_vs_ma5",
    "close_vs_ma10",
    "close_vs_ma20",
    "close_vs_ma60",
    "close_vs_ma240",
    "vol_vs_vma5",
    "vol_vs_vma10",
    "vol_vs_vma20",
    "ma5_vs_ma20",  # short vs medium trend
    "ma20_vs_ma60",  # medium vs long trend
    "k",
    "d",
    "rsi6",
    "rsi12",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "bb_position",  # (close - bb_lower) / (bb_upper - bb_lower): 0=bottom, 1=top
    "foreign_streak_days",
    "trust_streak_days",
    "dealer_streak_days",
]


def fetch_technical_features(
    symbols: list[str],
    as_of_date: str,
    close_series: "pd.Series | None" = None,
    volume_series: "pd.Series | None" = None,
) -> pd.DataFrame:
    """
    從資料庫撈取 as_of_date 當天或之前的最新技術指標，並計算衍生比值特徵。

    參數：
        symbols:       股票代碼列表。
        as_of_date:      PIT 基準日，使用 <= 此日期的最新一筆。
                       **必須傳 cutoff_date，不可傳 entry_date。** entry_date 在
                       正式執行時尚未發生，DB 沒資料所以看似無害；歷史重跑時
                       DB 早已涵蓋該日，同一段程式就會取到決策當下拿不到的列。
        close_series:  Optional Series（index=symbol），用於計算比值的收盤價。
                       若為 None，以 bb_middle 作為 bb_position 的代理收盤價。
        volume_series: Optional Series（index=symbol），用於 vol_vs_vma 比值計算。

    回傳：
        DataFrame，欄位為 ['symbol', 'tech_snapshot_date'] + TECHNICAL_FEATURE_COLS。
        tech_snapshot_date 為每檔實際取到的快照日，供呼叫端驗證 as-of 沒有越過
        cutoff（見 step2 的 assert_features_not_beyond_cutoff），驗完即丟。
    """
    if not symbols:
        return pd.DataFrame(
            columns=["symbol", "tech_snapshot_date"] + TECHNICAL_FEATURE_COLS
        )

    col_list = ", ".join(_TI_COLS)
    stmt = text(
        f"""
        WITH latest AS (
            SELECT symbol, date, {col_list},
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM technical_indicators
            WHERE symbol IN :symbols
              AND date <= :as_of_date
        )
        SELECT symbol, date, {col_list}
        FROM latest
        WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        ti = pd.read_sql(
            stmt, conn, params={"symbols": symbols, "as_of_date": as_of_date}
        )

    if ti.empty:
        raise RuntimeError(
            f"technical_indicators 在 as_of_date={as_of_date} 沒有任何 symbol 的資料 — "
            f"傳入 {len(symbols)} 個 symbols 全部無 PIT 技術指標。"
            "通常代表 DB 未匯入該日期或 calculator 未跑完，請補資料再執行。"
        )

    ti["symbol"] = ti["symbol"].astype(str).str.strip()
    for col in _TI_COLS:
        ti[col] = pd.to_numeric(ti[col], errors="coerce")

    # 使用傳入的收盤價／成交量，若無則以 bb_middle 替代。
    if close_series is not None:
        ti["_close"] = ti["symbol"].map(close_series)
    else:
        ti["_close"] = ti["bb_middle"]  # approximate

    if volume_series is not None:
        ti["_volume"] = ti["symbol"].map(volume_series)
    else:
        ti["_volume"] = np.nan

    def _ratio(num: pd.Series, denom: pd.Series) -> pd.Series:
        return (num / denom - 1.0).where(denom > 0)

    ti["close_vs_ma5"] = _ratio(ti["_close"], ti["ma5"])
    ti["close_vs_ma10"] = _ratio(ti["_close"], ti["ma10"])
    ti["close_vs_ma20"] = _ratio(ti["_close"], ti["ma20"])
    ti["close_vs_ma60"] = _ratio(ti["_close"], ti["ma60"])
    ti["close_vs_ma240"] = _ratio(ti["_close"], ti["ma240"])

    ti["vol_vs_vma5"] = _ratio(ti["_volume"], ti["vma5"])
    ti["vol_vs_vma10"] = _ratio(ti["_volume"], ti["vma10"])
    ti["vol_vs_vma20"] = _ratio(ti["_volume"], ti["vma20"])

    ti["ma5_vs_ma20"] = _ratio(ti["ma5"], ti["ma20"])
    ti["ma20_vs_ma60"] = _ratio(ti["ma20"], ti["ma60"])

    bb_range = ti["bb_upper"] - ti["bb_lower"]
    ti["bb_position"] = ((ti["_close"] - ti["bb_lower"]) / bb_range).where(bb_range > 0)

    # 不再 silent 補 NaN：TECHNICAL_FEATURE_COLS 全部在上方計算建立，
    # 若到這裡仍缺欄代表函式內部 bug，應直接 raise。
    missing_cols = [c for c in TECHNICAL_FEATURE_COLS if c not in ti.columns]
    if missing_cols:
        raise RuntimeError(
            f"fetch_technical_features 內部 bug：未建立欄位 {missing_cols}"
        )

    ti = ti.rename(columns={"date": "tech_snapshot_date"})
    return ti[["symbol", "tech_snapshot_date"] + TECHNICAL_FEATURE_COLS].reset_index(
        drop=True
    )


# ── 月營收特徵 ────────────────────────────────────────────────────────────────

REVENUE_FEATURE_COLS = [
    "revenue_yoy_1m",  # latest month YoY %
    "revenue_mom_1m",  # latest month MoM %
    "revenue_cum_yoy",  # cumulative YoY % (year-to-date)
    "revenue_yoy_3m_avg",  # 3-month average YoY %
    "revenue_yoy_accel",  # YoY acceleration: latest YoY - 3-month-ago YoY
]


def expected_revenue_month(as_of_date: str) -> str:
    """as_of_date 當下「應該」已經公告的最新月營收月份 = 當月的前一個月。

    台股月營收須於次月 10 日前申報，而 cutoff_date 落在當月 10 或 15 日，
    所以正常情況下最新可得的就是前一個月。回傳格式 "YYYYMXX"。
    """
    year, month = int(as_of_date[:4]), int(as_of_date[5:7])
    year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return f"{year}M{month:02d}"


def fetch_revenue_features(
    symbols: list[str],
    as_of_date: str,  # "YYYY-MM-DD"，一律傳 cutoff_date
) -> pd.DataFrame:
    """
    僅使用 as_of_date 當天或之前已發布的資料，撈取月營收特徵。

    PIT 安全：以 publish_time <= as_of_compact (YYYYMMDD) 過濾 monthly_revenue。
    cutoff_date 落在 M/10 或 M/15，可取得該日前已發布的營收，即涵蓋 M-1 月。

    **必須傳 cutoff_date，不可傳 entry_date。** 傳 entry_date 會把公告日之後才
    申報的營收放進來——2026-07 颱風延後申報那次，1838 筆 2026M06 有 192 筆落在
    cutoff 之後，決策當下拿不到。見 models_selection/2026-07-11/
    DIAG_lookahead_rev0713.md。

    回傳 DataFrame，欄位為 ['symbol', 'rev_max_publish_time'] + REVENUE_FEATURE_COLS。
    rev_max_publish_time 為該檔**所有撈回列**（rn 1–6）的 publish_time 上界
    （YYYYMMDD），供呼叫端驗證 as-of 沒有越過 cutoff，驗完即丟。

    注意稽核欄涵蓋的是「撈回列」不是「餵進特徵的列」——特徵只讀 rn 1–3
    （rn 1 / rn <= 3 / rn == 3），rn 4–6 撈了沒用。稽核欄仍取全部撈回列，因為
    上界取愈寬只會愈保守（SQL 已用 publish_time <= as_of 過濾，不會偽陽性），
    而且日後改動特徵公式的 rn 範圍時這一欄不必跟著改。
    缺少資料的股票，所有特徵欄位填 NaN。
    """
    if not symbols:
        return pd.DataFrame(
            columns=["symbol", "rev_max_publish_time"] + REVENUE_FEATURE_COLS
        )

    as_of_compact = as_of_date.replace("-", "")  # "YYYYMMDD"

    # 每個股票撈取最近 6 個月，以 publish_time 做 PIT 過濾。
    # monthly_revenue.date 格式為 "YYYYMXX"（如 "2025M09"），字母排序即為時間順序。
    stmt = text(
        """
        WITH rev AS (
            SELECT symbol, date, yoy_pct, mom_pct, cumulative_yoy_pct, publish_time,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM monthly_revenue
            WHERE symbol IN :symbols
              AND publish_time IS NOT NULL
              AND publish_time <= :as_of_compact
        )
        SELECT symbol, date, yoy_pct, mom_pct, cumulative_yoy_pct, publish_time, rn
        FROM rev
        WHERE rn <= 6
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        df = pd.read_sql(
            stmt, conn, params={"symbols": symbols, "as_of_compact": as_of_compact}
        )

    sym_df = pd.DataFrame({"symbol": [str(s) for s in symbols]})

    if df.empty:
        raise RuntimeError(
            f"monthly_revenue 在 publish_time <= {as_of_compact} 沒有任何資料 — "
            f"傳入 {len(symbols)} 個 symbols 全部無已發布月營收。"
            "通常代表 DB 未匯入或 publish_time 欄位為空，請補資料再執行。"
        )

    df["symbol"] = df["symbol"].astype(str).str.strip()
    for col in ["yoy_pct", "mom_pct", "cumulative_yoy_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 過期的股票一律填 NaN，不拿舊月份頂替。
    #
    # 若某檔到 cutoff 都還沒申報當期營收（遲報），rn=1 會是更早的月份。沿用它
    # 等於讓 revenue_yoy_1m 這個欄位對不同股票量到不同月份，而模型分不出來——
    # 2026-07 颱風那次，6727 亞泰金屬的 2026M06 遲至 07-13 才公告，回退到
    # 2026M05 的 +54.10%，但實際的 2026M06 是 −23.89%，方向完全相反。
    # 本模組對「完全沒有資料」的股票本來就填 NaN，過期理應比照辦理，
    # 而且 NaN 是 LightGBM 原生支援的。
    expected_month = expected_revenue_month(as_of_date)
    stale_symbols: list[str] = []

    records = []
    for sym, grp in df.groupby("symbol"):
        grp = grp.sort_values("rn").reset_index(drop=True)

        # 該檔所有撈回列的 publish_time 上界（str，YYYYMMDD 字典序 = 時間序），
        # 供 step2 驗證 as-of 沒有越過 cutoff。刻意不限縮到實際餵進特徵的
        # rn 1–3，理由見 docstring。
        max_publish = str(grp["publish_time"].max())

        r1 = grp[grp["rn"] == 1]
        latest_month = str(r1["date"].iloc[0]) if len(r1) else ""
        if latest_month < expected_month:
            stale_symbols.append(sym)
            records.append(
                {
                    "symbol": sym,
                    "rev_max_publish_time": max_publish,
                    **{c: np.nan for c in REVENUE_FEATURE_COLS},
                }
            )
            continue

        yoy_1m = (
            float(r1["yoy_pct"].iloc[0])
            if len(r1) and pd.notna(r1["yoy_pct"].iloc[0])
            else np.nan
        )
        mom_1m = (
            float(r1["mom_pct"].iloc[0])
            if len(r1) and pd.notna(r1["mom_pct"].iloc[0])
            else np.nan
        )
        cum_yoy = (
            float(r1["cumulative_yoy_pct"].iloc[0])
            if len(r1) and pd.notna(r1["cumulative_yoy_pct"].iloc[0])
            else np.nan
        )

        recent_3 = grp[grp["rn"] <= 3]["yoy_pct"].dropna()
        yoy_3m_avg = float(recent_3.mean()) if len(recent_3) >= 2 else np.nan

        r3 = grp[grp["rn"] == 3]
        yoy_3m_ago = (
            float(r3["yoy_pct"].iloc[0])
            if len(r3) and pd.notna(r3["yoy_pct"].iloc[0])
            else np.nan
        )
        yoy_accel = (
            (yoy_1m - yoy_3m_ago)
            if not (np.isnan(yoy_1m) or np.isnan(yoy_3m_ago))
            else np.nan
        )

        records.append(
            {
                "symbol": sym,
                "rev_max_publish_time": max_publish,
                "revenue_yoy_1m": yoy_1m,
                "revenue_mom_1m": mom_1m,
                "revenue_cum_yoy": cum_yoy,
                "revenue_yoy_3m_avg": yoy_3m_avg,
                "revenue_yoy_accel": yoy_accel,
            }
        )

    if stale_symbols:
        print(
            f"revenue features: {len(stale_symbols)}/{len(symbols)} symbols stale "
            f"(latest published month < {expected_month} as of {as_of_date}) -> NaN"
        )

    result = pd.DataFrame(records)
    result = sym_df.merge(result, on="symbol", how="left")
    for col in REVENUE_FEATURE_COLS:
        if col not in result.columns:
            result[col] = np.nan

    return result[
        ["symbol", "rev_max_publish_time"] + REVENUE_FEATURE_COLS
    ].reset_index(drop=True)
