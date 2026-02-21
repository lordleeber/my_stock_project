import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error

TARGET = "target_eps"
TARGET_DELTA = "delta_eps"
EXCLUDE_COLUMNS = {"year", TARGET, TARGET_DELTA}

BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train shared RF model for train_eps/<market>/<year>/<month>")
    parser.add_argument("--month-dir", type=Path, required=True, help="例如 train_eps/sii/2025/08")
    parser.add_argument("--dataset", type=Path, default=None, help="預設為 <month-dir>/dataset_train.csv")
    parser.add_argument("--model-out", type=Path, default=None, help="預設為 <month-dir>/model.pkl")
    parser.add_argument("--metrics-out", type=Path, default=None, help="預設為 <month-dir>/train_metrics.json")
    parser.add_argument("--importance-out", type=Path, default=None, help="預設為 <month-dir>/feature_importance.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--winsor-quantile", type=float, default=0.01)
    parser.add_argument("--n-jobs", type=int, default=-1)
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path]:
    month_dir = args.month_dir
    if not month_dir.is_absolute():
        month_dir = (Path.cwd() / month_dir).resolve()

    dataset = args.dataset if args.dataset else month_dir / "dataset_train.csv"
    model_out = args.model_out if args.model_out else month_dir / "model.pkl"
    metrics_out = args.metrics_out if args.metrics_out else month_dir / "train_metrics.json"
    importance_out = args.importance_out if args.importance_out else month_dir / "feature_importance.csv"

    return month_dir, dataset, model_out, metrics_out, importance_out


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
    month_dir, dataset_path, model_out, metrics_out, importance_out = resolve_paths(args)

    df = pd.read_csv(dataset_path).replace([np.inf, -np.inf], np.nan).dropna(subset=[TARGET, TARGET_DELTA])

    # 自動從訓練檔挑特徵欄位，避免每個月份手動維護 FEATURES
    feature_cols = [c for c in df.columns if c not in EXCLUDE_COLUMNS]
    if not feature_cols:
        raise ValueError("沒有可用特徵欄位，請檢查 dataset_train.csv")
    if "q2_eps" not in feature_cols:
        raise ValueError("dataset_train.csv 必須包含 q2_eps 欄位")

    for c in feature_cols:
        df[c] = df[c].fillna(0)

    winsor_cols = [c for c in feature_cols if c != "q2_eps"] + [TARGET_DELTA]
    winsorize_inplace(df, winsor_cols, args.winsor_quantile)

    x_data = df[feature_cols]
    y_delta = df[TARGET_DELTA].astype(float).to_numpy()

    model = RandomForestRegressor(
        n_estimators=400,
        max_depth=12,
        random_state=args.seed,
        criterion="absolute_error",
        n_jobs=args.n_jobs,
    )
    model.fit(x_data, y_delta)

    pred_eps = df["q2_eps"].to_numpy(dtype=float) + model.predict(x_data)
    baseline_eps = df["q2_eps"].to_numpy(dtype=float)
    y_true = df[TARGET].to_numpy(dtype=float)

    metrics = {
        "month_dir": str(month_dir),
        "n_rows": int(len(df)),
        "main_metric": "mae",
        "winsor_quantile": float(args.winsor_quantile),
        "train_mae_rf_pred_eps": float(mean_absolute_error(y_true, pred_eps)),
        "train_mae_baseline_q2_eps": float(mean_absolute_error(y_true, baseline_eps)),
        "features": feature_cols,
    }

    importance_df = pd.DataFrame({"feature": feature_cols, "importance": model.feature_importances_}).sort_values(
        "importance", ascending=False
    )

    model_out.parent.mkdir(parents=True, exist_ok=True)
    with open(model_out, "wb") as f:
        pickle.dump(model, f)
    metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    importance_df.to_csv(importance_out, index=False)

    print(f"train completed: {month_dir.name}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()


