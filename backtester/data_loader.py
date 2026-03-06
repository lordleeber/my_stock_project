from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from train_eps import prepare_data as tp


REQUIRED_CANDIDATE_COLUMNS = {"symbol", "predict_target_price", "close", "entry_date"}


def load_candidates(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"candidates not found: {path}")

    df = pd.read_csv(path)
    missing = REQUIRED_CANDIDATE_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"candidates missing required columns: {sorted(missing)}")

    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["entry_date"] = pd.to_datetime(out["entry_date"], errors="coerce")
    out["predict_target_price"] = pd.to_numeric(out["predict_target_price"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")

    out = out.dropna(subset=["symbol", "entry_date"])
    out = out[out["symbol"] != ""].copy()
    if out.empty:
        raise RuntimeError("candidates exists but has no usable symbol/entry_date rows")
    return out.reset_index(drop=True)


def normalize_quotes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=["symbol", "date"]).copy()
    return out.sort_values(["symbol", "date"]).drop_duplicates(subset=["symbol", "date"], keep="last").reset_index(drop=True)


def estimate_quote_window(candidates: pd.DataFrame, max_hold_days: int) -> tuple[str, str]:
    # A generous calendar buffer to cover trading-day-based max hold.
    start = candidates["entry_date"].min().date()
    end = candidates["entry_date"].max().date() + timedelta(days=max(60, max_hold_days * 3))
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def fetch_quotes_from_db(symbols: list[str], start_date: str, end_date: str) -> pd.DataFrame:
    if not symbols:
        raise ValueError("symbols is empty")

    stmt = text(
        """
        SELECT symbol, date, open, high, low, close
        FROM daily_quotes
        WHERE symbol IN :symbols
          AND date >= :start_date
          AND date <= :end_date
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(tp.get_db_url())
    with engine.connect() as conn:
        out = pd.read_sql(
            stmt,
            conn,
            params={"symbols": symbols, "start_date": start_date, "end_date": end_date},
        )
    return normalize_quotes(out)
