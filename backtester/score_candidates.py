"""
Apply trained selection model to score this month's candidates.

Input:  strategies/output/<year>/<month>/dataset_strategy.csv
        models_selection/latest/selection_model.pkl  (or --model-dir)
Output: strategies/output/<year>/<month>/candidates_scored.csv

Usage:
  venv/bin/python3 backtester/score_candidates.py --year 2025 --month 10
"""
from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score candidates using selection model.")
    parser.add_argument("--year",      type=int,  required=True)
    parser.add_argument("--month",     type=str,  required=True)
    parser.add_argument("--model-dir", type=Path, default=None,
                        help="Model dir (default: models_selection/latest)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    year  = int(args.year)
    month = str(args.month).zfill(2)

    ds_path  = (ROOT_DIR / "strategies" / "output" / f"{year:04d}" / month / "dataset_strategy.csv").resolve()
    out_path = (ROOT_DIR / "strategies" / "output" / f"{year:04d}" / month / "candidates_scored.csv").resolve()

    if not ds_path.exists():
        print(f"dataset_strategy.csv not found: {ds_path}")
        print("Run finalize_strategy.py first.")
        sys.exit(1)

    model_dir  = args.model_dir or (ROOT_DIR / "models_selection" / "latest").resolve()
    model_path = model_dir / "selection_model.pkl"
    if not model_path.exists():
        print(f"model not found: {model_path}")
        print("Run: venv/bin/python3 strategies/train_selection_model.py")
        sys.exit(1)

    with open(model_path, "rb") as f:
        payload = pickle.load(f)
    model        = payload["model"]
    feature_cols = payload["feature_cols"]

    df = pd.read_csv(ds_path)
    df["symbol"] = df["symbol"].astype(str).str.strip()

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        print(f"[WARN] features missing in dataset_strategy.csv (will be filled with 0): {missing}")

    for c in feature_cols:
        if c not in df.columns:
            df[c] = 0.0

    X = df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    df["ml_score"] = model.predict(X)
    df["ml_rank"]  = df["ml_score"].rank(ascending=False, method="first").astype(int)

    out = df.sort_values("ml_rank").reset_index(drop=True)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"scored {len(out)} candidates → {out_path}")
    show_cols = [c for c in ["symbol", "name", "ml_rank", "ml_score", "pred_upside_pct",
                             "pe_current", "ttm_eps", "close_vs_ma240"] if c in out.columns]
    print(f"\nTop 15 by ml_score:")
    print(out[show_cols].head(15).to_string(index=False))


if __name__ == "__main__":
    main()
