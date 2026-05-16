"""
合併 EPS 預測、解析進場日並補充技術指標，完成當月策略資料集。

讀取：
  strategies/output/<year>/<month>/dataset_strategy.csv
  models_eps/<year>/<month>/predictions_results.csv

寫入：
  strategies/output/<year>/<month>/dataset_strategy.csv  （原地更新，新增欄位）
  strategies/output/<year>/<month>/trade_candidates.csv  （供 run_rolling.py 使用）

用法：
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

from common.db import get_db_url

from strategies.feature_engineering import (
    fetch_technical_features,
    TECHNICAL_FEATURE_COLS,
    fetch_revenue_features,
    REVENUE_FEATURE_COLS,
)


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
    """回傳 earliest 當天或之後第一個實際交易日。"""
    stmt = text("SELECT MIN(date) FROM daily_quotes WHERE date >= :d")
    with engine.connect() as conn:
        row = conn.execute(stmt, {"d": earliest.strftime("%Y-%m-%d")}).fetchone()
    if row and row[0]:
        return str(row[0])
    return earliest.strftime("%Y-%m-%d")


def compute_pred_upside(df: pd.DataFrame, month: str) -> pd.DataFrame:
    """合併 EPS 預測 delta → 計算 predict_target_price → pred_upside_pct。"""
    df = df.copy()

    anchor = pd.to_numeric(df.get("anchor_eps"), errors="coerce")
    pred_delta = pd.to_numeric(df.get("pred_lgb_delta"), errors="coerce")
    df["predict_target_eps"] = anchor + pred_delta

    ttm = pd.to_numeric(df.get("ttm_eps"), errors="coerce")

    # TTM 滾動：把目前 TTM 視窗中最舊的那一季踢出、塞入 predict_target_eps。
    # 月份對應的 rolloff 季別需與 step1 compute_ttm_eps_by_month 的 playbook 一致。
    if month in {"05", "06", "07"}:
        ttm_rolloff_eps = pd.to_numeric(df.get("ly_q2_eps"), errors="coerce")
    elif month in {"08", "09", "10"}:
        ttm_rolloff_eps = pd.to_numeric(df.get("ly_q3_eps"), errors="coerce")
    elif month in {"11", "12", "01"}:
        ttm_rolloff_eps = pd.to_numeric(df.get("ly_q4_eps"), errors="coerce")
    else:
        ttm_rolloff_eps = pd.to_numeric(df.get("ly_q1_eps"), errors="coerce")

    df["ttm_eps_forward"] = ttm - ttm_rolloff_eps + df["predict_target_eps"]
    df["predict_target_price"] = (
        pd.to_numeric(df.get("pe_current"), errors="coerce") * df["ttm_eps_forward"]
    )
    close = pd.to_numeric(df.get("close"), errors="coerce")
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

    # 刪除先前計算過的欄位，確保重跑時結果一致（idempotent）。
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

    # 只保留預測檔的 pred_lgb_delta（其他欄位已在 ds 中）。
    pred_cols = ["symbol", "pred_lgb_delta"]
    pred_merge = pred[[c for c in pred_cols if c in pred.columns]].drop_duplicates(
        "symbol"
    )

    df = ds.merge(pred_merge, on="symbol", how="left")
    df = compute_pred_upside(df, month)

    # 解析進場日。
    rel_dt = release_date(year, month_int)
    earliest = rel_dt + timedelta(days=1)
    engine = create_engine(get_db_url())
    entry_date_str = resolve_entry_date(engine, earliest)
    df["entry_date"] = entry_date_str
    print(f"entry_date: {entry_date_str}")

    # 撈取 entry_date 的技術指標特徵。
    symbols = df["symbol"].tolist()
    close_s = pd.to_numeric(df.set_index("symbol")["close"], errors="coerce")
    # volume_lots 在 csv 內為單位「張」，技術指標 vma* 以「股」為單位，這裡轉回股數。
    volume_s = (
        pd.to_numeric(df.set_index("symbol")["volume_lots"], errors="coerce") * 1000.0
    )
    tech = fetch_technical_features(
        symbols, entry_date_str, close_series=close_s, volume_series=volume_s
    )
    # 刪除 df 中已存在的技術指標欄位，避免重複。
    existing_tech = [c for c in TECHNICAL_FEATURE_COLS if c in df.columns]
    if existing_tech:
        df = df.drop(columns=existing_tech)
    df = df.merge(tech, on="symbol", how="left")
    print(f"Technical features added: {len(TECHNICAL_FEATURE_COLS)} cols")

    # 撈取 entry_date 的月營收特徵（透過 publish_time 過濾，確保 PIT 安全）。
    rev = fetch_revenue_features(symbols, entry_date_str)
    existing_rev = [c for c in REVENUE_FEATURE_COLS if c in df.columns]
    if existing_rev:
        df = df.drop(columns=existing_rev)
    df = df.merge(rev, on="symbol", how="left")
    n_rev = df[REVENUE_FEATURE_COLS].notna().any(axis=1).sum()
    print(
        f"Revenue features added: {len(REVENUE_FEATURE_COLS)} cols  ({n_rev}/{len(df)} symbols with data)"
    )

    # close / ttm_eps / volume_lots 由 step1 emit 為 canonical 欄位，
    # step2 不再加同義別名（避免兩個入口同一份資料）。

    # 寫入更新後的 dataset_strategy.csv。
    df.to_csv(strategy_path, index=False, encoding="utf-8-sig")
    print(f"dataset_strategy.csv updated: {strategy_path}  ({len(df)} rows)")

    # 寫入 trade_candidates.csv。
    tc_cols = [
        "symbol",
        "predict_target_price",
        "close",
        "entry_date",
        "pred_upside_pct",
    ]
    tc = df[[c for c in tc_cols if c in df.columns]].copy()
    valid = (
        tc["predict_target_price"].notna()
        & tc["close"].notna()
        & tc["close"].gt(0)
        & tc["pred_upside_pct"].gt(0)
    )
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
