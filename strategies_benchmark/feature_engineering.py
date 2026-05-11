"""
Shared feature engineering for stock selection model.

Fetches pre-computed technical indicators from the technical_indicators table
and monthly revenue features from the monthly_revenue table,
for a set of symbols at a given reference date.

Used by:
  - analyze_feature_returns.py  (training data generation)
  - backtester/score_candidates.py  (production scoring)
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

# Columns to fetch from technical_indicators.
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

# Derived ratio features computed from raw TI values + close price.
# These are what actually go into the model.
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
    Fetch latest technical indicators from DB on or before ref_date,
    then compute derived ratio features.

    Args:
        symbols:       List of stock symbols.
        ref_date:      Reference date (entry_date). Use most recent row <= this date.
        close_series:  Optional Series (index=symbol) of close prices for ratio computation.
                       If None, uses bb_middle as close proxy for bb_position.
        volume_series: Optional Series (index=symbol) of volumes for vol_vs_vma ratios.

    Returns:
        DataFrame with columns ['symbol'] + TECHNICAL_FEATURE_COLS.
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

    # Use provided close/volume or fall back to bb_middle.
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


# ── Institutional Flow Features ──────────────────────────────────────────────

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
    Compute 5-day institutional net buy ratios (% of avg daily volume).

    foreign_net_5d       = sum(foreign_net, 5d) / avg(volume, 5d)
    trust_net_5d         = sum(trust_net, 5d) / avg(volume, 5d)
    smart_money_net_5d   = (sum(foreign_net, 5d) + sum(trust_net, 5d)) / avg(volume, 5d)

    Returns DataFrame with columns ['symbol'] + INSTITUTIONAL_FLOW_COLS.
    """
    if not symbols:
        return pd.DataFrame(columns=["symbol"] + INSTITUTIONAL_FLOW_COLS)

    # Fetch last 5 trading days of institutional data on or before ref_date.
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

    # Fetch last 5 trading days of volume from daily_quotes.
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

    result = sym_df.merge(
        agg[["symbol"] + INSTITUTIONAL_FLOW_COLS], on="symbol", how="left"
    )
    return result[["symbol"] + INSTITUTIONAL_FLOW_COLS].reset_index(drop=True)


# ── Price / Volatility Features ───────────────────────────────────────────────

PRICE_FEATURE_COLS = [
    "hist_vol_20d",
]


def fetch_price_features(
    symbols: list[str],
    ref_date: str,
) -> pd.DataFrame:
    """
    Compute 20-day annualised historical volatility from close prices.

    hist_vol_20d = std(daily_log_return, 20d) * sqrt(252)

    Returns DataFrame with columns ['symbol'] + PRICE_FEATURE_COLS.
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


# ── Monthly Revenue Features ──────────────────────────────────────────────────

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
    Fetch monthly revenue features using only data published on or before ref_date.

    PIT-safe: filters monthly_revenue by publish_time <= ref_date_compact (YYYYMMDD).
    For month M with entry_date ~M/11, this picks up revenue published through M/10,
    which covers month M-1's data (published by the 10th of M).

    Returns DataFrame with columns ['symbol'] + REVENUE_FEATURE_COLS.
    Missing symbols get NaN for all feature columns.
    """
    if not symbols:
        return pd.DataFrame(columns=["symbol"] + REVENUE_FEATURE_COLS)

    ref_compact = ref_date.replace("-", "")  # "YYYYMMDD"

    # Fetch up to 6 most recent months per symbol, PIT-filtered by publish_time.
    # monthly_revenue.date is "YYYYMXX" (e.g. "2025M09") — alphabetical sort is correct.
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

        # Positive YoY streak: consecutive months from most recent backward
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
