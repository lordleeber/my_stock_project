import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error


# V4 使用的特徵欄位
FEATURES = [
    "q2_eps",
    "ly_q3_eps",
    "q2_gross_margin",
    "q2_operating_margin",
    "q2_net_margin",
    "margin_momentum",
    "q2_non_op_ratio",
    "q2_roe",
    "q2_roa",
    "q2_debt_ratio",
    "q2_current_ratio",
    "q2_ocf_ratio",
    "q2_capex_intensity",
    "rev_trend_m8_m7",
    "rev_trend_m9_m8",
]
DATASET_PATH = Path(__file__).resolve().parent / "dataset.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest for analysis/v4")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def evaluate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    # 原則：主評分指標為 MAE，輔助指標僅保留 P90_AE（尾部風險）
    absolute_error = np.abs(y_true - y_pred)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "p90_ae": float(np.quantile(absolute_error, 0.9)),
    }


def main() -> None:
    args = parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATASET_PATH)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["target_eps", "year"])
    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    # 使用 expanding window 做時間回測
    unique_years = sorted(df["year"].astype(int).unique().tolist())
    test_years = unique_years[1:]

    fold_rows = []
    pred_rows = []

    for test_year in test_years:
        train_df = df[df["year"].astype(int) < test_year].copy()
        test_df = df[df["year"].astype(int) == test_year].copy()
        if train_df.empty or test_df.empty:
            continue

        # 原則：主評分指標使用 MAE，訓練目標也盡量對齊 MAE
        model = RandomForestRegressor(
            n_estimators=500,
            max_depth=15,
            random_state=args.seed,
            criterion="absolute_error",
            n_jobs=1,
        )
        model.fit(train_df[FEATURES], train_df["target_eps"])

        y_true = test_df["target_eps"].to_numpy(dtype=float)
        pred_rf = model.predict(test_df[FEATURES])
        pred_baseline_q2 = test_df["q2_eps"].astype(float).to_numpy()

        train_target_median = float(train_df["target_eps"].median())
        pred_baseline_median = np.full(len(test_df), train_target_median, dtype=float)

        model_predictions = [
            ("rf_vanilla", pred_rf),
            ("baseline_q2_eps", pred_baseline_q2),
            ("baseline_train_median", pred_baseline_median),
        ]

        for model_name, prediction_values in model_predictions:
            metric_values = evaluate_metrics(y_true, prediction_values)
            fold_rows.append(
                {
                    "version": "v4",
                    "protocol": "expanding_by_year",
                    "fold": f"year_{test_year}",
                    "model": model_name,
                    "mae": metric_values["mae"],
                    "p90_ae": metric_values["p90_ae"],
                    "n_train": len(train_df),
                    "n_test": len(test_df),
                }
            )

        prediction_columns = []
        if "year" in test_df.columns:
            prediction_columns.append("year")
        if "symbol" in test_df.columns:
            prediction_columns.append("symbol")
        if "name" in test_df.columns:
            prediction_columns.append("name")

        pred_detail_df = test_df[prediction_columns].copy()
        pred_detail_df["y_true"] = y_true
        pred_detail_df["pred_rf_vanilla"] = pred_rf
        pred_detail_df["pred_baseline_q2_eps"] = pred_baseline_q2
        pred_detail_df["pred_baseline_train_median"] = pred_baseline_median
        pred_detail_df["fold"] = f"year_{test_year}"
        pred_rows.append(pred_detail_df)

    fold_df = pd.DataFrame(fold_rows)

    if pred_rows:
        pred_df = pd.concat(pred_rows, ignore_index=True)
    else:
        pred_df = pd.DataFrame()

    fold_numeric_columns = fold_df.select_dtypes(include=[np.number]).columns.tolist()
    pred_numeric_columns = pred_df.select_dtypes(include=[np.number]).columns.tolist()

    fold_df[fold_numeric_columns] = fold_df[fold_numeric_columns].round(2)
    pred_df[pred_numeric_columns] = pred_df[pred_numeric_columns].round(2)

    fold_path = RESULTS_DIR / "backtest_by_fold.csv"
    pred_path = RESULTS_DIR / "predictions.csv"

    fold_df.to_csv(fold_path, index=False)
    pred_df.to_csv(pred_path, index=False)

    print("v4 backtest completed")
    print(f"- {fold_path}")
    print(f"- {pred_path}")


if __name__ == "__main__":
    main()
