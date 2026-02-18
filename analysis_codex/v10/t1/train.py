import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

FEATURES = [
    "q2_eps",
    "ly_q3_eps",
    "q2_margin",
    "q2_ocf_ratio",
    "q2_re_ratio",
    "rev_yoy_m7_z",
    "rev_m7_ratio_q2_z",
    "margin_momentum",
    "q2_roe",
    "q2_debt_ratio",
    "q2_non_op_ratio",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = BASE_DIR / "dataset.csv"
DEFAULT_MODEL = BASE_DIR / "model.pkl"
DEFAULT_METRICS = BASE_DIR / "train_metrics.json"
DEFAULT_IMPORTANCE = BASE_DIR / "feature_importance.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train v10_t1 model for analysis_codex.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--importance-out", type=Path, default=DEFAULT_IMPORTANCE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--winsor-quantile", type=float, default=0.01)
    return parser.parse_args()


def winsorize_inplace(df: pd.DataFrame, cols: list[str], q: float) -> None:
    if q <= 0:
        return
    low_q, high_q = q, 1.0 - q
    for c in cols:
        lo = float(df[c].quantile(low_q))
        hi = float(df[c].quantile(high_q))
        df[c] = df[c].clip(lower=lo, upper=hi)


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.dataset).replace([np.inf, -np.inf], np.nan).dropna(subset=[TARGET, TARGET_DELTA])
    for c in FEATURES:
        df[c] = df[c].fillna(0)

    winsor_cols = [c for c in FEATURES if c != "q2_eps"] + [TARGET_DELTA]
    winsorize_inplace(df, winsor_cols, args.winsor_quantile)

    X = df[FEATURES]
    y_delta = df[TARGET_DELTA].astype(float).to_numpy()

    model = RandomForestRegressor(n_estimators=400, max_depth=12, random_state=args.seed, criterion="absolute_error", n_jobs=-1)
    model.fit(X, y_delta)

    pred_eps = df["q2_eps"].to_numpy(dtype=float) + model.predict(X)
    baseline_eps = df["q2_eps"].to_numpy(dtype=float)
    y_true = df[TARGET].to_numpy(dtype=float)

    metrics = {
        "n_rows": int(len(df)),
        "main_metric": "mae",
        "winsor_quantile": float(args.winsor_quantile),
        "train_mae_rf_pred_eps": float(mean_absolute_error(y_true, pred_eps)),
        "train_mae_baseline_q2_eps": float(mean_absolute_error(y_true, baseline_eps)),
    }

    imp = pd.DataFrame({"feature": FEATURES, "importance": model.feature_importances_}).sort_values("importance", ascending=False)

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.model_out, "wb") as f:
        pickle.dump(model, f)
    args.metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    imp.to_csv(args.importance_out, index=False)

    print("v10_t1 train completed")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
