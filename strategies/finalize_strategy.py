"""
Finalize monthly strategy data by merging EPS predictions, resolving entry_date,
and fetching technical features.

Reads:
  strategies/output/<year>/<month>/dataset_strategy.csv
  models_eps/<year>/<month>/predictions_results.csv

Writes:
  strategies/output/<year>/<month>/dataset_strategy.csv  (updated in-place with new columns)
  strategies/output/<year>/<month>/trade_candidates.csv  (for run_rolling.py)

Usage:
  venv/bin/python3 strategies/finalize_strategy.py --year 2025 --month 10
"""

from __future__ import annotations

import argparse
import calendar
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.feature_engineering import (
    fetch_technical_features,
    TECHNICAL_FEATURE_COLS,
    fetch_revenue_features,
    REVENUE_FEATURE_COLS,
)
from train_eps import prepare_data as tp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalize strategy dataset and produce trade candidates."
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 08")
    return parser.parse_args()


def release_date(year: int, month: int) -> date:
    day = 15 if month in {5, 8, 11} else 10
    day = min(day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def resolve_entry_date(engine, earliest: date) -> str:
    """Return first actual trading day on or after earliest."""
    stmt = text("SELECT MIN(date) FROM daily_quotes WHERE date >= :d")
    with engine.connect() as conn:
        row = conn.execute(stmt, {"d": earliest.strftime("%Y-%m-%d")}).fetchone()
    if row and row[0]:
        return str(row[0])
    return earliest.strftime("%Y-%m-%d")


def compute_pred_upside(df: pd.DataFrame, month: str) -> pd.DataFrame:
    """Merge EPS prediction delta → predict_target_price → pred_upside_pct."""
    df = df.copy()

    anchor = pd.to_numeric(df.get("anchor_eps"), errors="coerce")
    pred_delta = pd.to_numeric(df.get("pred_lgb_delta"), errors="coerce")
    df["predict_target_eps"] = anchor + pred_delta

    ttm = pd.to_numeric(df.get("ttm_eps_official"), errors="coerce")

    if month in {"05", "06", "07"}:
        oldest = pd.to_numeric(df.get("ly_q2_eps"), errors="coerce")
    elif month in {"08", "09", "10"}:
        oldest = pd.to_numeric(df.get("ly_q3_eps"), errors="coerce")
    elif month in {"11", "12", "01"}:
        oldest = pd.to_numeric(df.get("ly_q4_eps"), errors="coerce")
    else:
        oldest = pd.to_numeric(df.get("ly_q1_eps"), errors="coerce")

    df["ttm_eps_forward"] = ttm - oldest + df["predict_target_eps"]
    df["predict_target_price"] = (
        pd.to_numeric(df.get("pe_current"), errors="coerce") * df["ttm_eps_forward"]
    )
    close = pd.to_numeric(df.get("q3_close"), errors="coerce")
    df["pred_upside_pct"] = (
        (df["predict_target_price"] - close) / close * 100.0
    ).where(close > 0)
    return df


def main() -> None:
    args = parse_args()
    year = int(args.year)
    month = str(args.month).zfill(2)
    month_int = int(month)

    out_dir = (ROOT_DIR / "strategies" / "output" / f"{year:04d}" / month).resolve()
    strategy_path = out_dir / "dataset_strategy.csv"
    pred_path = (
        ROOT_DIR / "models_eps" / f"{year:04d}" / month / "predictions_results.csv"
    ).resolve()
    candidates_path = out_dir / "trade_candidates.csv"

    if not strategy_path.exists():
        raise FileNotFoundError(
            f"dataset_strategy.csv not found: {strategy_path}\nRun prepare_data.py first."
        )
    if not pred_path.exists():
        raise FileNotFoundError(
            f"predictions_results.csv not found: {pred_path}\nRun predict_and_publish.py first."
        )

    ds = pd.read_csv(strategy_path)
    pred = pd.read_csv(pred_path)

    ds["symbol"] = ds["symbol"].astype(str).str.strip()
    pred["symbol"] = pred["symbol"].astype(str).str.strip()

    # Drop any previously computed columns so re-runs stay idempotent.
    RECOMPUTED_COLS = (
        [
            "pred_lgb_delta",
            "predict_target_eps",
            "ttm_eps_forward",
            "predict_target_price",
            "pred_upside_pct",
            "entry_date",
        ]
        + TECHNICAL_FEATURE_COLS
        + REVENUE_FEATURE_COLS
    )
    ds = ds.drop(columns=[c for c in RECOMPUTED_COLS if c in ds.columns])

    # Keep only pred_lgb_delta from predictions (other cols already in ds).
    pred_cols = ["symbol", "pred_lgb_delta"]
    pred_merge = pred[[c for c in pred_cols if c in pred.columns]].drop_duplicates(
        "symbol"
    )

    df = ds.merge(pred_merge, on="symbol", how="left")
    df = compute_pred_upside(df, month)

    # Resolve entry_date.
    rel_dt = release_date(year, month_int)
    earliest = rel_dt + timedelta(days=1)
    engine = create_engine(tp.get_db_url())
    entry_date_str = resolve_entry_date(engine, earliest)
    df["entry_date"] = entry_date_str
    print(f"entry_date: {entry_date_str}")

    # Fetch technical features at entry_date.
    symbols = df["symbol"].tolist()
    close_s = pd.to_numeric(df.set_index("symbol")["q3_close"], errors="coerce")
    volume_s = pd.to_numeric(df.set_index("symbol")["target_volume"], errors="coerce")
    tech = fetch_technical_features(
        symbols, entry_date_str, close_series=close_s, volume_series=volume_s
    )
    # Drop any tech cols already in df to avoid duplicates.
    existing_tech = [c for c in TECHNICAL_FEATURE_COLS if c in df.columns]
    if existing_tech:
        df = df.drop(columns=existing_tech)
    df = df.merge(tech, on="symbol", how="left")
    print(f"Technical features added: {len(TECHNICAL_FEATURE_COLS)} cols")

    # Fetch monthly revenue features at entry_date (PIT-safe via publish_time filter).
    rev = fetch_revenue_features(symbols, entry_date_str)
    existing_rev = [c for c in REVENUE_FEATURE_COLS if c in df.columns]
    if existing_rev:
        df = df.drop(columns=existing_rev)
    df = df.merge(rev, on="symbol", how="left")
    n_rev = df[REVENUE_FEATURE_COLS].notna().any(axis=1).sum()
    print(
        f"Revenue features added: {len(REVENUE_FEATURE_COLS)} cols  ({n_rev}/{len(df)} symbols with data)"
    )

    # Convenience aliases for downstream scripts (analyze, score, train).
    df["close"] = pd.to_numeric(df.get("q3_close"), errors="coerce")
    df["ttm_eps"] = pd.to_numeric(df.get("ttm_eps_official"), errors="coerce")
    df["volume_lots"] = pd.to_numeric(df.get("target_volume"), errors="coerce") / 1000.0

    # Write updated dataset_strategy.csv.
    df.to_csv(strategy_path, index=False, encoding="utf-8-sig")
    print(f"dataset_strategy.csv updated: {strategy_path}  ({len(df)} rows)")

    # Write trade_candidates.csv.
    tc_cols = [
        "symbol",
        "predict_target_price",
        "q3_close",
        "entry_date",
        "pred_upside_pct",
    ]
    tc = df[[c for c in tc_cols if c in df.columns]].copy()
    tc = tc.rename(columns={"q3_close": "close"})
    valid = tc["predict_target_price"].notna() & tc["close"].notna() & tc["close"].gt(0)
    tc = (
        tc[valid].sort_values("pred_upside_pct", ascending=False).reset_index(drop=True)
    )
    tc.to_csv(candidates_path, index=False, encoding="utf-8-sig")

    print(f"trade_candidates.csv written: {candidates_path}  ({len(tc)} rows)")
    print("\nTop 10 by pred_upside_pct:")
    print(tc.head(10).to_string(index=False))

    print("\nfinalize_strategy done")
    print(f"- year: {year}, month: {month}")
    print(f"- strategy rows: {len(df)}")
    print(f"- trade_candidates rows: {len(tc)}")


if __name__ == "__main__":
    main()
