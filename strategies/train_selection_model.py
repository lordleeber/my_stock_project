"""
Train a stock selection model (LightGBM Ranker, lambdarank) using historical
feature-return pairs.

Ranking objective:
  Within each month, stocks are assigned a relevance label (0 = worst return,
  n-1 = best return). LightGBM learns to rank stocks within a month so the
  highest-labelled ones appear at the top.

Input:  strategies/output/feature_return_analysis.csv
Output: models_selection/<cutoff_year>/<cutoff_month>/selection_model.pkl
                                                      feature_importance.csv
                                                      latest.json

Walk-forward design:
  - Train on data where (year, month) <= cutoff
  - Evaluate on data where (year, month) > cutoff
  - Default cutoff: all available data (for production use)

Usage:
  # Train on all data (production)
  venv/bin/python3 strategies/train_selection_model.py

  # Walk-forward evaluation
  venv/bin/python3 strategies/train_selection_model.py --cutoff-year 2024 --cutoff-month 6
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import lightgbm as lgb
except ImportError:
    print("lightgbm not installed. Run: pip install lightgbm")
    sys.exit(1)

from strategies.feature_engineering import TECHNICAL_FEATURE_COLS, REVENUE_FEATURE_COLS

FEATURE_COLS = [
    "pred_upside_pct",
    "pe_current",
    "ttm_eps",
    "volume_lots",
    "foreign_held_ratio",
    "trust_held_ratio",
    "large_holder_ratio",
    "large_holder_ratio_wow",
    "large_holder_two_week_up",
    "mid_holder_ratio",
    "mid_holder_ratio_wow",
    "small_holder_ratio",
    "small_holder_ratio_wow",
    "concentration_spread",
    "concentration_spread_wow",
    # valuation
    "roe_official",
    "pe_percentile_official",
    # market sentiment
    "dealer_held_ratio",
    "margin_usage_ratio",
    "short_cover_pressure",
    "sbl_sell_repay_ratio",
    # fundamental quality
    "anchor_debt_ratio",
    "pb_ratio",
    "current_ratio",
    "eps_acc_yoy",
    "revenue_acc_yoy",
] + TECHNICAL_FEATURE_COLS + REVENUE_FEATURE_COLS  # includes close_vs_ma5/10/20/60/240, k, d, rsi, macd, bb_position, revenue momentum, etc.

LABEL_COL = "fwd_return_pct"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LightGBM Ranker for stock selection.")
    parser.add_argument("--cutoff-year",   type=int,   default=None)
    parser.add_argument("--cutoff-month",  type=int,   default=None)
    parser.add_argument("--n-estimators",  type=int,   default=200)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--num-leaves",    type=int,   default=15)
    parser.add_argument("--n-bins",        type=int,   default=5,
                        help="Number of label bins per month (default 5=quintile, 10=decile)")
    return parser.parse_args()


def build_rank_labels(df: pd.DataFrame, n_bins: int = 5) -> pd.Series:
    """
    Within each (year, month) group, assign relevance label 0-(n_bins-1).
    Highest return bucket = label n_bins-1, lowest = label 0.
    LightGBM lambdarank maximises NDCG, so higher label = should rank higher.
    """
    labels = list(range(n_bins))

    def _bin(g: pd.Series) -> pd.Series:
        try:
            return pd.qcut(g, n_bins, labels=labels, duplicates="drop").astype(int)
        except Exception:
            return (g >= g.median()).astype(int)

    return df.groupby(["year", "month"], group_keys=False)[LABEL_COL].apply(_bin)


def build_groups(df: pd.DataFrame) -> list[int]:
    """Return list of group sizes (stocks per month), in row order."""
    return df.groupby(["year", "month"], sort=False).size().tolist()


def spearman_ic(df: pd.DataFrame, pred: np.ndarray) -> float:
    """Overall Spearman IC between model scores and actual returns."""
    return pd.Series(pred).corr(pd.Series(df[LABEL_COL].values), method="spearman")


def monthly_ic(df: pd.DataFrame, pred: np.ndarray) -> pd.DataFrame:
    """Per-month Spearman IC."""
    tmp = df[["year", "month", LABEL_COL]].copy()
    tmp["pred"] = pred
    ic = (
        tmp.groupby(["year", "month"])
        .apply(lambda g: g["pred"].corr(g[LABEL_COL], method="spearman"), include_groups=False)
        .reset_index(name="ic")
    )
    return ic


def main() -> None:
    args = parse_args()

    data_path = (ROOT_DIR / "strategies" / "output" / "feature_return_analysis.csv").resolve()
    if not data_path.exists():
        print(f"Training data not found: {data_path}")
        print("Run: venv/bin/python3 strategies/analyze_feature_returns.py")
        sys.exit(1)

    df = pd.read_csv(data_path)
    df["year"]  = pd.to_numeric(df["year"],  errors="coerce").astype("Int64")
    df["month"] = df["month"].astype(str).str.zfill(2)
    df["ym"]    = df["year"].astype(int) * 100 + df["month"].astype(int)

    # Must sort so rows are contiguous within each month (required by LGBMRanker group).
    df = df.sort_values(["year", "month"]).reset_index(drop=True)

    # Walk-forward split.
    if args.cutoff_year is not None and args.cutoff_month is not None:
        cutoff_ym    = args.cutoff_year * 100 + args.cutoff_month
        train_df     = df[df["ym"] <= cutoff_ym].copy()
        eval_df      = df[df["ym"] >  cutoff_ym].copy()
        cutoff_label = f"{args.cutoff_year:04d}/{args.cutoff_month:02d}"
    else:
        train_df     = df.copy()
        eval_df      = pd.DataFrame()
        cutoff_label = "all"

    print(f"Training data: {len(train_df)} rows  ({train_df['ym'].nunique()} months)  cutoff={cutoff_label}")
    if not eval_df.empty:
        print(f"Eval data:     {len(eval_df)} rows  ({eval_df['ym'].nunique()} months)")

    feat_cols = [c for c in FEATURE_COLS if c in train_df.columns]
    missing   = [c for c in FEATURE_COLS if c not in train_df.columns]
    if missing:
        print(f"[WARN] features not in training data (will be skipped): {missing}")

    X_train      = train_df[feat_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    y_train      = build_rank_labels(train_df, n_bins=args.n_bins)
    train_groups = build_groups(train_df)

    model = lgb.LGBMRanker(
        objective="lambdarank",
        n_estimators=args.n_estimators,
        learning_rate=args.learning_rate,
        num_leaves=args.num_leaves,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=5,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_train, y_train, group=train_groups)

    train_pred = model.predict(X_train)
    train_ic   = spearman_ic(train_df, train_pred)
    print(f"Train Spearman IC: {train_ic:.4f}")

    eval_ic = None
    if not eval_df.empty:
        X_eval    = eval_df[feat_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
        eval_pred = model.predict(X_eval)
        eval_ic   = spearman_ic(eval_df, eval_pred)
        print(f"Eval  Spearman IC: {eval_ic:.4f}")

        mic = monthly_ic(eval_df, eval_pred)
        print(f"\nMonthly IC (eval period)  mean={mic['ic'].mean():.4f}  std={mic['ic'].std():.4f}:")
        print(mic.to_string(index=False))

    # Feature importance.
    importance = pd.DataFrame({
        "feature":          feat_cols,
        "importance_gain":  model.booster_.feature_importance(importance_type="gain"),
        "importance_split": model.booster_.feature_importance(importance_type="split"),
    }).sort_values("importance_gain", ascending=False)
    print("\nFeature importance (gain, top 20):")
    print(importance.head(20).to_string(index=False))

    # Save model.
    if args.cutoff_year is not None and args.cutoff_month is not None:
        out_dir = (ROOT_DIR / "models_selection" / f"{args.cutoff_year:04d}" / f"{args.cutoff_month:02d}").resolve()
    else:
        out_dir = (ROOT_DIR / "models_selection" / "latest").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "selection_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_cols": feat_cols}, f)

    importance.to_csv(out_dir / "feature_importance.csv", index=False)

    meta = {
        "model_path":        str(model_path),
        "objective":         "lambdarank",
        "feature_cols":      feat_cols,
        "cutoff":            cutoff_label,
        "train_rows":        int(len(train_df)),
        "train_months":      int(train_df["ym"].nunique()),
        "train_spearman_ic": round(float(train_ic), 4),
        "eval_spearman_ic":  round(float(eval_ic), 4) if eval_ic is not None else None,
        "params": {
            "n_estimators":  args.n_estimators,
            "learning_rate": args.learning_rate,
            "num_leaves":    args.num_leaves,
        },
    }
    (out_dir / "latest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nModel saved: {model_path}")


if __name__ == "__main__":
    main()
