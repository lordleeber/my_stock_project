import argparse
import json
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
    parser = argparse.ArgumentParser(description="Backtest for analysis/v8_t3")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--confidence-quantile", type=float, default=0.95)
    parser.add_argument("--eps-floor", type=float, default=0.20)
    parser.add_argument("--min-ttm-eps", type=float, default=2.0)
    parser.add_argument("--min-volume-lots", type=float, default=500.0)
    return parser.parse_args()


def mae_or_nan(values: np.ndarray) -> float:
    valid = values[~np.isnan(values)]
    if len(valid) == 0:
        return float("nan")
    return float(np.mean(np.abs(valid)))


def percentile_rank(series: pd.Series, value: float) -> float:
    if series.empty or np.isnan(value):
        return float("nan")
    rank = (series <= value).mean()
    return float(rank)


def predict_with_uncertainty(model: RandomForestRegressor, x_data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    x_np = x_data.to_numpy(dtype=float)
    tree_preds = np.vstack([tree.predict(x_np) for tree in model.estimators_])
    return tree_preds.mean(axis=0), tree_preds.std(axis=0)


def build_valuation_daily_frame(
    df_eval: pd.DataFrame,
    pred_eps: np.ndarray,
    model_version: str,
    source_file: str,
) -> pd.DataFrame:
    out = pd.DataFrame()
    out["date"] = df_eval["q3_date"] if "q3_date" in df_eval.columns else pd.Series([np.nan] * len(df_eval))
    out["symbol"] = df_eval["symbol"] if "symbol" in df_eval.columns else pd.Series([np.nan] * len(df_eval))
    out["close"] = df_eval["q3_close"] if "q3_close" in df_eval.columns else pd.Series([np.nan] * len(df_eval))
    out["volume"] = df_eval["q3_volume"] if "q3_volume" in df_eval.columns else pd.Series([np.nan] * len(df_eval))

    ttm_official = df_eval["ttm_eps_official"].to_numpy(dtype=float)
    target_eps = df_eval[TARGET].to_numpy(dtype=float)

    # 以「替換該季 EPS」方式取得 forward TTM
    ttm_forward = ttm_official - target_eps + pred_eps

    out["ttm_eps_official"] = ttm_official
    out["ttm_eps_forward"] = ttm_forward

    close = out["close"].to_numpy(dtype=float)
    pe_official = np.full(len(out), np.nan, dtype=float)
    pe_forward = np.full(len(out), np.nan, dtype=float)

    mask_official = (~np.isnan(close)) & (np.abs(ttm_official) > 1e-9)
    mask_forward = (~np.isnan(close)) & (np.abs(ttm_forward) > 1e-9)

    pe_official[mask_official] = close[mask_official] / ttm_official[mask_official]
    pe_forward[mask_forward] = close[mask_forward] / ttm_forward[mask_forward]

    out["pe_official"] = pe_official
    out["pe_forward"] = pe_forward

    pe_official_series = pd.Series(pe_official)
    pe_forward_series = pd.Series(pe_forward)

    out["pe_percentile_official"] = [percentile_rank(pe_official_series.dropna(), v) for v in pe_official]
    out["pe_percentile_forward"] = [percentile_rank(pe_forward_series.dropna(), v) for v in pe_forward]

    pe_current = df_eval["pe_current"].to_numpy(dtype=float) if "pe_current" in df_eval.columns else np.full(len(df_eval), np.nan)
    target_price = pred_eps * pe_current
    upside_pct = np.where((~np.isnan(close)) & (close > 0), (target_price / close - 1.0) * 100.0, np.nan)

    out["predict_target_price"] = target_price
    out["upside_pct"] = upside_pct

    out["roe_official"] = df_eval["q2_roe"] if "q2_roe" in df_eval.columns else np.nan
    roe_forward = np.full(len(out), np.nan, dtype=float)
    if "q2_roe" in df_eval.columns and "q2_eps" in df_eval.columns:
        q2_eps = df_eval["q2_eps"].to_numpy(dtype=float)
        q2_roe = df_eval["q2_roe"].to_numpy(dtype=float)
        mask_roe = np.abs(q2_eps) > 1e-9
        roe_forward[mask_roe] = (pred_eps[mask_roe] / q2_eps[mask_roe]) * q2_roe[mask_roe]
    out["roe_forward"] = roe_forward

    # 可追溯欄位（PCED）
    out["pced_file"] = source_file
    out["pced_row"] = np.arange(len(out))
    out["pced_col"] = "pred_rf_delta"
    out["model_version"] = model_version

    return out


def quality_check_and_report(df_val: pd.DataFrame, report_path: Path) -> None:
    checks = {}

    for col in ["date", "symbol", "close", "ttm_eps_official", "ttm_eps_forward", "pe_official", "pe_forward", "predict_target_price", "upside_pct"]:
        if col in df_val.columns:
            checks[f"null_rate__{col}"] = float(df_val[col].isna().mean())

    numeric_cols = [c for c in df_val.columns if pd.api.types.is_numeric_dtype(df_val[c])]
    for col in numeric_cols:
        arr = df_val[col].to_numpy(dtype=float)
        inf_rate = float(np.mean(np.isinf(arr)))
        checks[f"inf_rate__{col}"] = inf_rate

    checks["rows"] = int(len(df_val))
    checks["symbols"] = int(df_val["symbol"].nunique()) if "symbol" in df_val.columns else 0

    report_path.write_text(json.dumps(checks, indent=2), encoding="utf-8")


def evaluate_metrics(df_eval: pd.DataFrame, y_true: np.ndarray, y_pred: np.ndarray, eps_floor: float) -> dict:
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

    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "p90_ae": float(np.quantile(abs_err, 0.9)),
        "pe_forward_err_mae": mae_or_nan(pred_forward_pe - true_forward_pe),
        "target_price_err_mae": mae_or_nan(pred_target_price - true_target_price),
        "upside_pct_err_mae": mae_or_nan(pred_upside - true_upside),
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
    valuation_rows = []

    for test_year in test_years:
        train_df = df[df["year"].astype(int) < test_year].copy()
        test_df = df[df["year"].astype(int) == test_year].copy()
        if train_df.empty or test_df.empty:
            continue

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
        _, pred_delta_train_std = predict_with_uncertainty(model, train_df[FEATURES])
        confidence_threshold = float(np.quantile(pred_delta_train_std, args.confidence_quantile))
        pred_delta_hybrid = np.where(pred_delta_std > confidence_threshold, 0.0, pred_delta_raw)
        pred_eps_rf = test_df["q2_eps"].to_numpy(dtype=float) + pred_delta_hybrid

        pred_eps_baseline_q2 = test_df["q2_eps"].to_numpy(dtype=float)
        pred_eps_baseline_median = np.full(len(test_df), float(train_df[TARGET].median()), dtype=float)

        model_predictions = [
            ("rf_delta", pred_eps_rf),
            ("baseline_q2_eps", pred_eps_baseline_q2),
            ("baseline_train_median", pred_eps_baseline_median),
        ]

        for model_name, pred_eps in model_predictions:
            metric_values = evaluate_metrics(test_df, y_true, pred_eps, args.eps_floor)
            fold_rows.append(
                {
                    "version": "v8_t3",
                    "protocol": "expanding_by_year",
                    "fold": f"year_{test_year}",
                    "model": model_name,
                    "mae": metric_values["mae"],
                    "p90_ae": metric_values["p90_ae"],
                    "pe_forward_err_mae": metric_values["pe_forward_err_mae"],
                    "target_price_err_mae": metric_values["target_price_err_mae"],
                    "upside_pct_err_mae": metric_values["upside_pct_err_mae"],
                    "n_train": len(train_df),
                    "n_test": len(test_df),
                }
            )

        keep_cols = [c for c in ["year", "symbol", "name", "q3_date", "q3_close", "q3_volume", "pe_current", "ttm_eps_official"] if c in test_df.columns]
        pred_detail_df = test_df[keep_cols].copy()
        pred_detail_df["y_true"] = y_true
        pred_detail_df["pred_rf_delta"] = pred_eps_rf
        pred_detail_df["pred_delta_std"] = pred_delta_std
        pred_detail_df["confidence_threshold"] = confidence_threshold
        pred_detail_df["pred_baseline_q2_eps"] = pred_eps_baseline_q2
        pred_detail_df["pred_baseline_train_median"] = pred_eps_baseline_median
        pred_detail_df["fold"] = f"year_{test_year}"
        pred_rows.append(pred_detail_df)

        val_df = build_valuation_daily_frame(
            df_eval=test_df,
            pred_eps=pred_eps_rf,
            model_version="v8_t3",
            source_file="analysis_codex/v8/t3/results/predictions.csv",
        )
        val_df["fold"] = f"year_{test_year}"
        valuation_rows.append(val_df)

    fold_df = pd.DataFrame(fold_rows)
    pred_df = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    valuation_df = pd.concat(valuation_rows, ignore_index=True) if valuation_rows else pd.DataFrame()

    fold_num_cols = fold_df.select_dtypes(include=[np.number]).columns.tolist()
    pred_num_cols = pred_df.select_dtypes(include=[np.number]).columns.tolist()
    val_num_cols = valuation_df.select_dtypes(include=[np.number]).columns.tolist()

    fold_df[fold_num_cols] = fold_df[fold_num_cols].round(2)
    pred_df[pred_num_cols] = pred_df[pred_num_cols].round(2)
    valuation_df[val_num_cols] = valuation_df[val_num_cols].round(4)

    # 實務交易過濾：忽略 TTM EPS < 2 與日成交量 < 500 張
    if not valuation_df.empty:
        ttm_ok = valuation_df["ttm_eps_forward"] >= float(args.min_ttm_eps)
        volume_lots = valuation_df["volume"] / 1000.0
        volume_ok = volume_lots >= float(args.min_volume_lots)
        valuation_df = valuation_df[ttm_ok & volume_ok].copy()

    fold_path = RESULTS_DIR / "backtest_by_fold.csv"
    pred_path = RESULTS_DIR / "predictions.csv"
    valuation_path = RESULTS_DIR / "valuation_daily_preview.csv"
    quality_path = RESULTS_DIR / "valuation_quality_report.json"

    fold_df.to_csv(fold_path, index=False)
    pred_df.to_csv(pred_path, index=False)
    valuation_df.to_csv(valuation_path, index=False)
    quality_check_and_report(valuation_df, quality_path)

    print("v8_t3 backtest completed")
    print(f"- {fold_path}")
    print(f"- {pred_path}")
    print(f"- {valuation_path}")
    print(f"- {quality_path}")


if __name__ == "__main__":
    main()
