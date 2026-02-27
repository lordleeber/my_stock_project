import argparse
import json
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from sklearn.metrics import mean_absolute_error

TARGET = "target_eps"
TARGET_DELTA = "delta_eps"
EXCLUDE_COLUMNS = {"year", TARGET, TARGET_DELTA}

BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train shared LightGBM model for train_eps/<market>/<year>/<month>")
    parser.add_argument("--market", type=str, required=True, choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="01~12")
    parser.add_argument("--dataset", type=Path, default=None, help="預設為 <month-dir>/dataset_train.csv")
    parser.add_argument("--model-out", type=Path, default=None, help="預設為 <month-dir>/model.pkl")
    parser.add_argument("--metrics-out", type=Path, default=None, help="預設為 <month-dir>/train_metrics.json")
    parser.add_argument("--importance-out", type=Path, default=None, help="預設為 <month-dir>/feature_importance.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--winsor-quantile", type=float, default=0.01)
    parser.add_argument("--n-jobs", type=int, default=-1)
    parser.add_argument("--n-estimators", type=int, default=800)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    parser.add_argument("--num-leaves", type=int, default=31)
    parser.add_argument("--subsample", type=float, default=0.8)
    parser.add_argument("--colsample-bytree", type=float, default=0.8)
    parser.add_argument("--reg-alpha", type=float, default=0.0)
    parser.add_argument("--reg-lambda", type=float, default=0.0)
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path]:
    month_str = str(args.month).zfill(2)
    if month_str < "01" or month_str > "12":
        raise ValueError("--month 必須是 01~12")
    month_dir = (Path.cwd() / "train_eps" / args.market / str(args.year) / month_str).resolve()

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
    if "anchor_eps" not in feature_cols:
        raise ValueError("dataset_train.csv 必須包含 anchor_eps 欄位")
    z_features = [c for c in feature_cols if c.endswith("_z")]
    if z_features:
        raise ValueError(
            "dataset_train.csv 不可包含 *_z 欄位。請先執行新版 prepare_data.py，輸出 *_quantile 後再訓練。"
        )
    quantile_features = [c for c in feature_cols if c.endswith("_quantile")]
    if not quantile_features:
        raise ValueError(
            "dataset_train.csv 缺少 *_quantile 特徵。請先執行新版 prepare_data.py。"
        )

    # prepare_data 已完成特徵轉換，train 只讀取最終特徵
    use_features = feature_cols

    for c in use_features:
        df[c] = df[c].fillna(0)

    winsor_cols = [c for c in use_features if c != "anchor_eps"] + [TARGET_DELTA]
    winsorize_inplace(df, winsor_cols, args.winsor_quantile)

    x_data = df[use_features]
    y_delta = df[TARGET_DELTA].astype(float).to_numpy()

    model = LGBMRegressor(
        objective="mae",
        n_estimators=args.n_estimators,
        learning_rate=args.learning_rate,
        num_leaves=args.num_leaves,
        subsample=args.subsample,
        colsample_bytree=args.colsample_bytree,
        reg_alpha=args.reg_alpha,
        reg_lambda=args.reg_lambda,
        random_state=args.seed,
        n_jobs=args.n_jobs,
    )
    model.fit(x_data, y_delta)

    pred_eps = df["anchor_eps"].to_numpy(dtype=float) + model.predict(x_data)
    baseline_eps = df["anchor_eps"].to_numpy(dtype=float)
    y_true = df[TARGET].to_numpy(dtype=float)

    metrics = {
        "month_dir": str(month_dir),
        "n_rows": int(len(df)),
        "main_metric": "mae",
        "winsor_quantile": float(args.winsor_quantile),
        "model_family": "lightgbm",
        "train_mae_lgb_pred_eps": float(mean_absolute_error(y_true, pred_eps)),
        "train_mae_rf_pred_eps": float(mean_absolute_error(y_true, pred_eps)),
        "train_mae_baseline_anchor_eps": float(mean_absolute_error(y_true, baseline_eps)),
        "feature_transform": "quantile",
        "features": use_features,
    }

    importance_df = pd.DataFrame({"feature": use_features, "importance": model.feature_importances_}).sort_values(
        "importance", ascending=False
    )

    model_out.parent.mkdir(parents=True, exist_ok=True)
    with open(model_out, "wb") as f:
        pickle.dump(model, f)
    metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    importance_df.to_csv(importance_out, index=False)

    # sanity check: in-sample MAE 應低於 baseline，否則代表訓練有嚴重問題
    rf_mae = metrics["train_mae_lgb_pred_eps"]
    bl_mae = metrics["train_mae_baseline_anchor_eps"]
    if rf_mae > bl_mae:
        log_path = BASE_DIR.parent / "error_train_eps.log"
        ts = datetime.now().isoformat(timespec="seconds")
        msg = (
            f"[{ts}] SANITY FAIL | {month_dir}\n"
            f"  train_mae_lgb_pred_eps ({rf_mae:.4f}) > train_mae_baseline_anchor_eps ({bl_mae:.4f})\n"
            f"  模型 in-sample 表現劣於 baseline，請確認 feature/label 是否正確串接。\n"
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg)
        print(f"[WARNING] sanity check failed — 詳見 {log_path}")

    print(f"train completed: {month_dir.name}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
