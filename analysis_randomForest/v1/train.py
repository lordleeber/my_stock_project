import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error


# V1 使用的特徵與目標欄位
FEATURES = ["q2_rev", "q2_margin", "q2_eps", "q3_rev_total"]
TARGET = "target_eps"

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = BASE_DIR / "dataset.csv"
DEFAULT_MODEL = BASE_DIR / "model.pkl"
DEFAULT_METRICS = BASE_DIR / "train_metrics.json"
DEFAULT_IMPORTANCE = BASE_DIR / "feature_importance.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train v1 model for analysis_codex.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--importance-out", type=Path, default=DEFAULT_IMPORTANCE)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 讀資料並做最基本清理
    df = pd.read_csv(args.dataset)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[TARGET])
    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    X = df[FEATURES]
    y = df[TARGET].astype(float).to_numpy()

    # 原則：主評分指標使用 MAE，訓練目標也盡量對齊 MAE
    model = RandomForestRegressor(
        n_estimators=300,
        random_state=args.seed,
        criterion="absolute_error",
    )
    model.fit(X, y)

    # 訓練集上，僅輸出 MAE 以避免同時看太多指標造成判斷混亂
    pred_train_rf = model.predict(X)
    pred_train_baseline = df["q2_eps"].astype(float).to_numpy()

    metrics = {
        "n_rows": int(len(df)),
        "main_metric": "mae",
        "train_mae_rf": float(mean_absolute_error(y, pred_train_rf)),
        "train_mae_baseline_q2_eps": float(mean_absolute_error(y, pred_train_baseline)),
    }

    # 輸出特徵重要度，方便判讀模型主要依賴哪些訊號
    importance_df = pd.DataFrame(
        {
            "feature": FEATURES,
            "importance": model.feature_importances_,
        }
    ).sort_values("importance", ascending=False)

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.model_out, "wb") as model_file:
        pickle.dump(model, model_file)
    args.metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    importance_df.to_csv(args.importance_out, index=False)

    print("v1 train completed")
    print(f"- dataset: {args.dataset}")
    print(f"- model: {args.model_out}")
    print(f"- metrics: {args.metrics_out}")
    print(f"- feature importance: {args.importance_out}")
    print(json.dumps(metrics, indent=2))
    print("top feature importances:")
    print(importance_df.head(5).to_string(index=False))


if __name__ == "__main__":
    main()
