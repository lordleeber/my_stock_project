from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from pathlib import Path
from typing import Iterable

import pandas as pd
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Connection, Engine

# Reuse shared DB URL source used by strategies/train pipelines.
ROOT_DIR = Path(__file__).resolve().parent.parent
import sys

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from train_eps import prepare_data as tp


REQUIRED_OHLC_COLS = ["open", "high", "low", "close"]
BASE_QUOTE_COLS = [
    "date",
    "symbol",
    "name",
    "market",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "value",
    "transactions",
    "change",
    "direction",
    "bid",
    "ask",
]


@dataclass
class QuoteQualityReport:
    input_rows: int
    rows_after_dropna_ohlc: int
    rows_after_sort_dedup: int
    dropped_due_to_missing_ohlc: int


def get_engine(db_url: str | None = None) -> Engine:
    url = db_url or tp.get_db_url()
    return create_engine(url)


def normalize_quotes(
    df: pd.DataFrame,
    *,
    drop_missing_ohlc: bool = True,
) -> tuple[pd.DataFrame, QuoteQualityReport]:
    out = df.copy()
    for c in BASE_QUOTE_COLS:
        if c not in out.columns:
            out[c] = pd.NA
    out = out[[c for c in BASE_QUOTE_COLS if c in out.columns]].copy()

    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in REQUIRED_OHLC_COLS + ["volume", "value", "transactions", "change", "bid", "ask"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    input_rows = len(out)
    if drop_missing_ohlc:
        out = out.dropna(subset=REQUIRED_OHLC_COLS)
    rows_after_dropna_ohlc = len(out)

    out = (
        out.sort_values(["symbol", "date"])
        .drop_duplicates(subset=["symbol", "date"], keep="last")
        .reset_index(drop=True)
    )
    rows_after_sort_dedup = len(out)

    report = QuoteQualityReport(
        input_rows=input_rows,
        rows_after_dropna_ohlc=rows_after_dropna_ohlc,
        rows_after_sort_dedup=rows_after_sort_dedup,
        dropped_due_to_missing_ohlc=input_rows - rows_after_dropna_ohlc,
    )
    return out, report


def fetch_daily_quotes(
    conn: Connection,
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
    *,
    drop_missing_ohlc: bool = True,
) -> tuple[pd.DataFrame, QuoteQualityReport]:
    symbol_list = sorted({str(s).strip() for s in symbols if str(s).strip()})
    if not symbol_list:
        empty = pd.DataFrame(columns=BASE_QUOTE_COLS)
        return normalize_quotes(empty, drop_missing_ohlc=drop_missing_ohlc)

    stmt = text(
        """
        SELECT
          date, symbol, name, market, open, high, low, close, volume,
          value, transactions, change, direction, bid, ask
        FROM daily_quotes
        WHERE symbol IN :symbols
          AND date >= :start_date
          AND date <= :end_date
        """
    ).bindparams(bindparam("symbols", expanding=True))

    raw = pd.read_sql(
        stmt,
        conn,
        params={"symbols": symbol_list, "start_date": start_date, "end_date": end_date},
    )
    return normalize_quotes(raw, drop_missing_ohlc=drop_missing_ohlc)


def load_daily_quotes(
    symbols: Iterable[str],
    start_date: str,
    end_date: str,
    *,
    db_url: str | None = None,
    drop_missing_ohlc: bool = True,
) -> tuple[pd.DataFrame, QuoteQualityReport]:
    engine = get_engine(db_url=db_url)
    with engine.connect() as conn:
        return fetch_daily_quotes(
            conn,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            drop_missing_ohlc=drop_missing_ohlc,
        )


def trading_days_between(
    quotes: pd.DataFrame,
    *,
    start_date: str | pd.Timestamp | date_type,
    end_date: str | pd.Timestamp | date_type,
    symbol: str | None = None,
) -> list[pd.Timestamp]:
    if quotes.empty:
        return []
    q = quotes
    if symbol is not None:
        q = q[q["symbol"].astype(str).str.strip() == str(symbol).strip()]
    if q.empty:
        return []
    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)
    if pd.isna(start_ts) or pd.isna(end_ts):
        return []
    if start_ts > end_ts:
        return []
    days = sorted(q[(q["date"] >= start_ts) & (q["date"] <= end_ts)]["date"].dropna().unique())
    return [pd.Timestamp(d) for d in days]


def next_trading_day(
    quotes: pd.DataFrame,
    *,
    on_or_after: str | pd.Timestamp | date_type,
    symbol: str | None = None,
) -> pd.Timestamp | None:
    if quotes.empty:
        return None
    q = quotes
    if symbol is not None:
        q = q[q["symbol"].astype(str).str.strip() == str(symbol).strip()]
    if q.empty:
        return None
    target = pd.to_datetime(on_or_after)
    if pd.isna(target):
        return None
    future = q[q["date"] >= target]["date"].dropna().sort_values()
    if future.empty:
        return None
    return pd.Timestamp(future.iloc[0])

