"""
選股模型的共用特徵工程模組。

依指定基準日，從 technical_indicators 撈取預計算的技術指標，
並從 monthly_revenue 撈取月營收特徵。

被以下腳本使用：
  - analyze_feature_returns.py  （訓練資料生成）
  - backtester/score_candidates.py  （生產選股評分）
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

from train_eps import prepare_data as tp

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
    ref_date: str,
    close_series: "pd.Series | None" = None,
    volume_series: "pd.Series | None" = None,
) -> pd.DataFrame:
    """
    從資料庫撈取 ref_date 當天或之前的最新技術指標，並計算衍生比值特徵。

    參數：
        symbols:       股票代碼列表。
        ref_date:      基準日（entry_date），使用 <= 此日期的最新一筆。
        close_series:  Optional Series（index=symbol），用於計算比值的收盤價。
                       若為 None，以 bb_middle 作為 bb_position 的代理收盤價。
        volume_series: Optional Series（index=symbol），用於 vol_vs_vma 比值計算。

    回傳：
        DataFrame，欄位為 ['symbol'] + TECHNICAL_FEATURE_COLS。
    """
    if not symbols:
        return pd.DataFrame(columns=["symbol"] + TECHNICAL_FEATURE_COLS)

    col_list = ", ".join(_TI_COLS)
    stmt = text(
        f"""
        WITH latest AS (
            SELECT symbol, date, {col_list},
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM technical_indicators
            WHERE symbol IN :symbols
              AND date <= :ref_date
        )
        SELECT symbol, date, {col_list}
        FROM latest
        WHERE rn = 1
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(tp.get_db_url())
    with engine.connect() as conn:
        ti = pd.read_sql(stmt, conn, params={"symbols": symbols, "ref_date": ref_date})

    if ti.empty:
        return pd.DataFrame(columns=["symbol"] + TECHNICAL_FEATURE_COLS)

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

    for col in TECHNICAL_FEATURE_COLS:
        if col not in ti.columns:
            ti[col] = np.nan

    return ti[["symbol"] + TECHNICAL_FEATURE_COLS].reset_index(drop=True)


# ── 法人買賣超特徵 ────────────────────────────────────────────────────────────

INSTITUTIONAL_FLOW_COLS = [
    "foreign_net_5d",
    "trust_net_5d",
    "smart_money_net_5d",
]


def fetch_institutional_flow_features(
    symbols: list[str],
    ref_date: str,
) -> pd.DataFrame:
    """
    計算 5 日法人淨買入比率（佔日均成交量的百分比）。

    foreign_net_5d       = sum(foreign_net, 5d) / avg(volume, 5d)
    trust_net_5d         = sum(trust_net, 5d) / avg(volume, 5d)
    smart_money_net_5d   = (sum(foreign_net, 5d) + sum(trust_net, 5d)) / avg(volume, 5d)

    回傳 DataFrame，欄位為 ['symbol'] + INSTITUTIONAL_FLOW_COLS。
    """
    if not symbols:
        return pd.DataFrame(columns=["symbol"] + INSTITUTIONAL_FLOW_COLS)

    # 撈取 ref_date 當天或之前最近 5 個交易日的法人資料。
    ii_stmt = text(
        """
        WITH ranked AS (
            SELECT symbol, date, foreign_net, trust_net,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM institutional_investors
            WHERE symbol IN :symbols
              AND date <= :ref_date
        )
        SELECT symbol, date, foreign_net, trust_net
        FROM ranked WHERE rn <= 5
        """
    ).bindparams(bindparam("symbols", expanding=True))

    # 從 daily_quotes 撈取最近 5 個交易日的成交量。
    dq_stmt = text(
        """
        WITH ranked AS (
            SELECT symbol, date, volume,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM daily_quotes
            WHERE symbol IN :symbols
              AND date <= :ref_date
              AND volume IS NOT NULL AND volume > 0
        )
        SELECT symbol, date, volume
        FROM ranked WHERE rn <= 5
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(tp.get_db_url())
    with engine.connect() as conn:
        ii_df = pd.read_sql(
            ii_stmt, conn, params={"symbols": symbols, "ref_date": ref_date}
        )
        dq_df = pd.read_sql(
            dq_stmt, conn, params={"symbols": symbols, "ref_date": ref_date}
        )

    sym_df = pd.DataFrame({"symbol": [str(s) for s in symbols]})

    if ii_df.empty or dq_df.empty:
        for col in INSTITUTIONAL_FLOW_COLS:
            sym_df[col] = np.nan
        return sym_df

    ii_df["symbol"] = ii_df["symbol"].astype(str).str.strip()
    dq_df["symbol"] = dq_df["symbol"].astype(str).str.strip()
    for col in ["foreign_net", "trust_net"]:
        ii_df[col] = pd.to_numeric(ii_df[col], errors="coerce")
    dq_df["volume"] = pd.to_numeric(dq_df["volume"], errors="coerce")

    ii_agg = ii_df.groupby("symbol").agg(
        foreign_net_sum=("foreign_net", "sum"),
        trust_net_sum=("trust_net", "sum"),
    )
    dq_agg = dq_df.groupby("symbol").agg(avg_volume=("volume", "mean"))

    agg = ii_agg.join(dq_agg, how="outer").reset_index()

    def _flow_ratio(net_sum: pd.Series, avg_vol: pd.Series) -> pd.Series:
        return (net_sum / avg_vol).where(avg_vol > 0)

    agg["foreign_net_5d"] = _flow_ratio(agg["foreign_net_sum"], agg["avg_volume"])
    agg["trust_net_5d"] = _flow_ratio(agg["trust_net_sum"], agg["avg_volume"])
    agg["smart_money_net_5d"] = _flow_ratio(
        agg["foreign_net_sum"] + agg["trust_net_sum"], agg["avg_volume"]
    )

    result = sym_df.merge(agg[["symbol"] + INSTITUTIONAL_FLOW_COLS], on="symbol", how="left")
    return result[["symbol"] + INSTITUTIONAL_FLOW_COLS].reset_index(drop=True)


# ── 價格 / 波動率特徵 ─────────────────────────────────────────────────────────

PRICE_FEATURE_COLS = [
    "hist_vol_20d",
]


def fetch_price_features(
    symbols: list[str],
    ref_date: str,
) -> pd.DataFrame:
    """
    從收盤價計算 20 日年化歷史波動率。

    hist_vol_20d = std(daily_log_return, 20d) * sqrt(252)

    回傳 DataFrame，欄位為 ['symbol'] + PRICE_FEATURE_COLS。
    """
    if not symbols:
        return pd.DataFrame(columns=["symbol"] + PRICE_FEATURE_COLS)

    stmt = text(
        """
        WITH ranked AS (
            SELECT symbol, date, close,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM daily_quotes
            WHERE symbol IN :symbols
              AND date <= :ref_date
              AND close IS NOT NULL AND close > 0
        )
        SELECT symbol, date, close
        FROM ranked WHERE rn <= 21
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(tp.get_db_url())
    with engine.connect() as conn:
        df = pd.read_sql(stmt, conn, params={"symbols": symbols, "ref_date": ref_date})

    sym_df = pd.DataFrame({"symbol": [str(s) for s in symbols]})

    if df.empty:
        sym_df["hist_vol_20d"] = np.nan
        return sym_df

    df["symbol"] = df["symbol"].astype(str).str.strip()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")

    records = []
    for sym, grp in df.groupby("symbol"):
        grp = grp.sort_values("date").reset_index(drop=True)
        closes = grp["close"].dropna().values
        if len(closes) < 2:
            records.append({"symbol": sym, "hist_vol_20d": np.nan})
            continue
        log_returns = np.diff(np.log(closes))
        hist_vol = float(np.std(log_returns, ddof=1) * np.sqrt(252))
        records.append({"symbol": sym, "hist_vol_20d": hist_vol})

    result = sym_df.merge(pd.DataFrame(records), on="symbol", how="left")
    return result[["symbol"] + PRICE_FEATURE_COLS].reset_index(drop=True)


# ── 月營收特徵 ────────────────────────────────────────────────────────────────

REVENUE_FEATURE_COLS = [
    "revenue_yoy_1m",  # latest month YoY %
    "revenue_mom_1m",  # latest month MoM %
    "revenue_cum_yoy",  # cumulative YoY % (year-to-date)
    "revenue_yoy_3m_avg",  # 3-month average YoY %
    "revenue_yoy_accel",  # YoY acceleration: latest YoY - 3-month-ago YoY
    "revenue_positive_streak",  # consecutive months of positive YoY (from latest backward)
]


def fetch_revenue_features(
    symbols: list[str],
    ref_date: str,  # "YYYY-MM-DD" (entry_date)
) -> pd.DataFrame:
    """
    僅使用 ref_date 當天或之前已發布的資料，撈取月營收特徵。

    PIT 安全：以 publish_time <= ref_date_compact (YYYYMMDD) 過濾 monthly_revenue。
    對於 entry_date 約在 M/11 的月份 M，可取得 M/10 前已發布的營收資料，
    即涵蓋 M-1 月的資料（於 M 月 10 日前發布）。

    回傳 DataFrame，欄位為 ['symbol'] + REVENUE_FEATURE_COLS。
    缺少資料的股票，所有特徵欄位填 NaN。
    """
    if not symbols:
        return pd.DataFrame(columns=["symbol"] + REVENUE_FEATURE_COLS)

    ref_compact = ref_date.replace("-", "")  # "YYYYMMDD"

    # 每個股票撈取最近 6 個月，以 publish_time 做 PIT 過濾。
    # monthly_revenue.date 格式為 "YYYYMXX"（如 "2025M09"），字母排序即為時間順序。
    stmt = text(
        """
        WITH rev AS (
            SELECT symbol, date, yoy_pct, mom_pct, cumulative_yoy_pct,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
            FROM monthly_revenue
            WHERE symbol IN :symbols
              AND publish_time IS NOT NULL
              AND publish_time != ''
              AND publish_time <= :ref_compact
        )
        SELECT symbol, date, yoy_pct, mom_pct, cumulative_yoy_pct, rn
        FROM rev
        WHERE rn <= 6
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(tp.get_db_url())
    with engine.connect() as conn:
        df = pd.read_sql(
            stmt, conn, params={"symbols": symbols, "ref_compact": ref_compact}
        )

    sym_df = pd.DataFrame({"symbol": [str(s) for s in symbols]})

    if df.empty:
        for col in REVENUE_FEATURE_COLS:
            sym_df[col] = np.nan
        return sym_df

    df["symbol"] = df["symbol"].astype(str).str.strip()
    for col in ["yoy_pct", "mom_pct", "cumulative_yoy_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    records = []
    for sym, grp in df.groupby("symbol"):
        grp = grp.sort_values("rn").reset_index(drop=True)

        r1 = grp[grp["rn"] == 1]
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

        # 正 YoY 連續月數：從最新月份往前連續計算
        streak = 0
        for _, row in grp.sort_values("rn").iterrows():
            v = row["yoy_pct"]
            if pd.isna(v) or v <= 0:
                break
            streak += 1

        records.append(
            {
                "symbol": sym,
                "revenue_yoy_1m": yoy_1m,
                "revenue_mom_1m": mom_1m,
                "revenue_cum_yoy": cum_yoy,
                "revenue_yoy_3m_avg": yoy_3m_avg,
                "revenue_yoy_accel": yoy_accel,
                "revenue_positive_streak": float(streak),
            }
        )

    result = pd.DataFrame(records)
    result = sym_df.merge(result, on="symbol", how="left")
    for col in REVENUE_FEATURE_COLS:
        if col not in result.columns:
            result[col] = np.nan

    return result[["symbol"] + REVENUE_FEATURE_COLS].reset_index(drop=True)
