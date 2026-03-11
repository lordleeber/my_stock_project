"""
Shared feature engineering for stock selection model.

Fetches pre-computed technical indicators from the technical_indicators table
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
    "ma5", "ma10", "ma20", "ma60", "ma240",
    "vma5", "vma10", "vma20",
    "k", "d", "rsi6", "rsi12",
    "macd_dif", "macd_dea", "macd_hist",
    "bb_upper", "bb_middle", "bb_lower",
    "foreign_streak_days", "trust_streak_days", "dealer_streak_days",
]

# Derived ratio features computed from raw TI values + close price.
# These are what actually go into the model.
TECHNICAL_FEATURE_COLS = [
    "close_vs_ma5", "close_vs_ma10", "close_vs_ma20", "close_vs_ma60", "close_vs_ma240",
    "vol_vs_vma5", "vol_vs_vma10", "vol_vs_vma20",
    "ma5_vs_ma20",       # short vs medium trend
    "ma20_vs_ma60",      # medium vs long trend
    "k", "d", "rsi6", "rsi12",
    "macd_dif", "macd_dea", "macd_hist",
    "bb_position",       # (close - bb_lower) / (bb_upper - bb_lower): 0=bottom, 1=top
    "foreign_streak_days", "trust_streak_days", "dealer_streak_days",
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

    ti["close_vs_ma5"]   = _ratio(ti["_close"], ti["ma5"])
    ti["close_vs_ma10"]  = _ratio(ti["_close"], ti["ma10"])
    ti["close_vs_ma20"]  = _ratio(ti["_close"], ti["ma20"])
    ti["close_vs_ma60"]  = _ratio(ti["_close"], ti["ma60"])
    ti["close_vs_ma240"] = _ratio(ti["_close"], ti["ma240"])

    ti["vol_vs_vma5"]  = _ratio(ti["_volume"], ti["vma5"])
    ti["vol_vs_vma10"] = _ratio(ti["_volume"], ti["vma10"])
    ti["vol_vs_vma20"] = _ratio(ti["_volume"], ti["vma20"])

    ti["ma5_vs_ma20"]  = _ratio(ti["ma5"],  ti["ma20"])
    ti["ma20_vs_ma60"] = _ratio(ti["ma20"], ti["ma60"])

    bb_range = ti["bb_upper"] - ti["bb_lower"]
    ti["bb_position"] = ((ti["_close"] - ti["bb_lower"]) / bb_range).where(bb_range > 0)

    for col in TECHNICAL_FEATURE_COLS:
        if col not in ti.columns:
            ti[col] = np.nan

    return ti[["symbol"] + TECHNICAL_FEATURE_COLS].reset_index(drop=True)
