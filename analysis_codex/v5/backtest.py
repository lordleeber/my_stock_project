import argparse
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
    "rev_trend_m8_m7",
    "rev_trend_m9_m8",
    "margin_momentum",
    "q2_roe",
    "q2_debt_ratio",
    "q2_non_op_ratio",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

DATASET_PATH = Path(__file__).resolve().parent / "dataset.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest for analysis/v5")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--winsor-quantile", type=float, default=0.01)
    parser.add_argument("--confidence-quantile", type=float, default=0.95)
    parser.add_argument("--eps-floor", type=float, default=0.20)
    parser.add_argument("--error-clip-quantile", type=float, default=0.99)
    return parser.parse_args()


def mae_from_error(err: np.ndarray, clip_q: float) -> float:
    valid = err[~np.isnan(err)]
    if len(valid) == 0:
        return float("nan")
    if clip_q < 1.0:
        bound = float(np.quantile(np.abs(valid), clip_q))
        valid = np.clip(valid, -bound, bound)
    return float(np.mean(np.abs(valid)))


def winsorize_train_test(train_df: pd.DataFrame, test_df: pd.DataFrame, cols: list[str], q: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if q <= 0:
        return train_df, test_df

    train_out = train_df.copy()
    test_out = test_df.copy()

    low_q = q
    high_q = 1.0 - q

    for col in cols:
        low = float(train_out[col].quantile(low_q))
        high = float(train_out[col].quantile(high_q))
        train_out[col] = train_out[col].clip(lower=low, upper=high)
        test_out[col] = test_out[col].clip(lower=low, upper=high)

    return train_out, test_out


def predict_with_uncertainty(model: RandomForestRegressor, X: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    X_np = X.to_numpy(dtype=float)
    tree_preds = np.vstack([tree.predict(X_np) for tree in model.estimators_])
    mean_pred = tree_preds.mean(axis=0)
    std_pred = tree_preds.std(axis=0)
    return mean_pred, std_pred


def evaluate_metrics(df_eval: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, eps_floor: float, error_clip_q: float) -> dict:
    abs_err = np.abs(y_true - y_pred)

    close = df_eval["q3_close"].to_numpy(dtype=float) if "q3_close" in df_eval.columns else np.full(len(df_eval), np.nan)
    pe_current = df_eval["pe_current"].to_numpy(dtype=float) if "pe_current" in df_eval.columns else np.full(len(df_eval), np.nan)

    valid_price = (~np.isnan(close)) & (close > 0)
    valid_pe = (~np.isnan(pe_current)) & (pe_current > 0)

    true_forward_pe = np.full(len(df_eval), np.nan)
    pred_forward_pe = np.full(len(df_eval), np.nan)

    eps_true_ok = np.abs(y_true) >= eps_floor
    eps_pred_ok = np.abs(y_pred) >= eps_floor

    mask_true_pe = valid_price & eps_true_ok
    mask_pred_pe = valid_price & eps_pred_ok

    true_forward_pe[mask_true_pe] = close[mask_true_pe] / y_true[mask_true_pe]
    pred_forward_pe[mask_pred_pe] = close[mask_pred_pe] / y_pred[mask_pred_pe]

    true_target_price = np.full(len(df_eval), np.nan)
    pred_target_price = np.full(len(df_eval), np.nan)
    mask_target = valid_pe
    true_target_price[mask_target] = y_true[mask_target] * pe_current[mask_target]
    pred_target_price[mask_target] = y_pred[mask_target] * pe_current[mask_target]

    true_upside = np.full(len(df_eval), np.nan)
    pred_upside = np.full(len(df_eval), np.nan)
    mask_upside = valid_price & (~np.isnan(true_target_price)) & (~np.isnan(pred_target_price))
    true_upside[mask_upside] = (true_target_price[mask_upside] / close[mask_upside] - 1.0) * 100.0
    pred_upside[mask_upside] = (pred_target_price[mask_upside] / close[mask_upside] - 1.0) * 100.0

    pe_forward_error = pred_forward_pe - true_forward_pe
    target_price_error = pred_target_price - true_target_price
    upside_error = pred_upside - true_upside

    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "p90_ae": float(np.quantile(abs_err, 0.9)),
        "pe_forward_err_mae": mae_from_error(pe_forward_error, error_clip_q),
        "target_price_err_mae": mae_from_error(target_price_error, error_clip_q),
        "upside_pct_err_mae": mae_from_error(upside_error, error_clip_q),
    }


def main() -> None:
    args = parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATASET_PATH)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[TARGET, TARGET_DELTA, "year", "q2_eps"])
    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    years = sorted(df["year"].astype(int).unique().tolist())
    test_years = years[1:]

    fold_rows = []
    pred_rows = []

    for test_year in test_years:
        train_df_raw = df[df["year"].astype(int) < test_year].copy()
        test_df_raw = df[df["year"].astype(int) == test_year].copy()
        if train_df_raw.empty or test_df_raw.empty:
            continue

        # v5.1: 用 train 統計量 winsorize train/test，降低極端值影響
        train_df, test_df = winsorize_train_test(train_df_raw, test_df_raw, FEATURES + [TARGET_DELTA], args.winsor_quantile)

        model = RandomForestRegressor(
            n_estimators=400,
            max_depth=12,
            random_state=args.seed,
            criterion="absolute_error",
            n_jobs=-1,
        )
        model.fit(train_df[FEATURES], train_df[TARGET_DELTA])

        y_true = test_df[TARGET].to_numpy(dtype=float)

        pred_delta_raw, pred_delta_std = predict_with_uncertainty(model, test_df[FEATURES])
        pred_eps_raw = test_df["q2_eps"].to_numpy(dtype=float) + pred_delta_raw

        # v5.1: 低信心樣本回退 baseline（delta=0）
        train_delta_mean, train_delta_std = predict_with_uncertainty(model, train_df[FEATURES])
        confidence_threshold = float(np.quantile(train_delta_std, args.confidence_quantile))

        pred_delta_hybrid = np.where(pred_delta_std > confidence_threshold, 0.0, pred_delta_raw)
        pred_eps_hybrid = test_df["q2_eps"].to_numpy(dtype=float) + pred_delta_hybrid

        pred_eps_baseline_q2 = test_df["q2_eps"].to_numpy(dtype=float)
        pred_eps_baseline_median = np.full(len(test_df), float(train_df[TARGET].median()), dtype=float)

        model_predictions = [
            ("rf_delta_raw", pred_eps_raw),
            ("rf_delta_hybrid", pred_eps_hybrid),
            ("baseline_q2_eps", pred_eps_baseline_q2),
            ("baseline_train_median", pred_eps_baseline_median),
        ]

        for model_name, pred_eps in model_predictions:
            metric_values = evaluate_metrics(test_df, y_true, pred_eps, args.eps_floor, args.error_clip_quantile)
            fold_rows.append(
                {
                    "version": "v5",
                    "protocol": "expanding_by_year",
                    "fold": f"year_{test_year}",
                    "model": model_name,
                    "mae": metric_values["mae"],
                    "p90_ae": metric_values["p90_ae"],
                    "pe_forward_err_mae": metric_values["pe_forward_err_mae"],
                    "target_price_err_mae": metric_values["target_price_err_mae"],
                    "upside_pct_err_mae": metric_values["upside_pct_err_mae"],
                    "confidence_threshold": confidence_threshold,
                    "n_train": len(train_df),
                    "n_test": len(test_df),
                }
            )

        keep_cols = []
        for col in ["year", "symbol", "name", "q3_close", "pe_current"]:
            if col in test_df.columns:
                keep_cols.append(col)

        pred_detail_df = test_df[keep_cols].copy()
        pred_detail_df["y_true"] = y_true
        pred_detail_df["pred_rf_delta_raw"] = pred_eps_raw
        pred_detail_df["pred_rf_delta_hybrid"] = pred_eps_hybrid
        pred_detail_df["pred_baseline_q2_eps"] = pred_eps_baseline_q2
        pred_detail_df["pred_baseline_train_median"] = pred_eps_baseline_median
        pred_detail_df["pred_delta_std"] = pred_delta_std
        pred_detail_df["confidence_threshold"] = confidence_threshold
        pred_detail_df["fold"] = f"year_{test_year}"
        pred_rows.append(pred_detail_df)

    fold_df = pd.DataFrame(fold_rows)
    pred_df = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()

    fold_num_cols = fold_df.select_dtypes(include=[np.number]).columns.tolist()
    pred_num_cols = pred_df.select_dtypes(include=[np.number]).columns.tolist()

    fold_df[fold_num_cols] = fold_df[fold_num_cols].round(2)
    pred_df[pred_num_cols] = pred_df[pred_num_cols].round(2)

    fold_path = RESULTS_DIR / "backtest_by_fold.csv"
    pred_path = RESULTS_DIR / "predictions.csv"

    fold_df.to_csv(fold_path, index=False)
    pred_df.to_csv(pred_path, index=False)

    print("v5 backtest completed")
    print(f"- {fold_path}")
    print(f"- {pred_path}")


if __name__ == "__main__":
    main()
