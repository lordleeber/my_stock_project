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
    "rev_volatility",
]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

DATASET_PATH = Path(__file__).resolve().parent / "dataset.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest for analysis_codex/v7")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--eps-floor", type=float, default=0.20)
    parser.add_argument("--min-regime-samples", type=int, default=120)
    parser.add_argument("--confidence-quantile", type=float, default=0.95)
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
    return float((series <= value).mean())


def build_regime_label(df: pd.DataFrame, margin_cut: float, vol_cut: float) -> pd.Series:
    margin_side = np.where(df["q2_margin"].to_numpy(dtype=float) >= margin_cut, "high_margin", "low_margin")
    vol_side = np.where(df["rev_volatility"].to_numpy(dtype=float) >= vol_cut, "high_vol", "low_vol")
    return pd.Series(margin_side + "__" + vol_side, index=df.index)


def fit_rf(x_train: pd.DataFrame, y_train: np.ndarray, seed: int) -> RandomForestRegressor:
    model = RandomForestRegressor(
        n_estimators=500,
        max_depth=12,
        random_state=seed,
        criterion="absolute_error",
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    return model


def predict_with_uncertainty(model: RandomForestRegressor, x_data: pd.DataFrame | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x_np = x_data.to_numpy(dtype=float) if isinstance(x_data, pd.DataFrame) else np.asarray(x_data, dtype=float)
    tree_preds = np.vstack([tree.predict(x_np) for tree in model.estimators_])
    return tree_preds.mean(axis=0), tree_preds.std(axis=0)


def train_regime_bundle(train_df: pd.DataFrame, seed: int, min_regime_samples: int, confidence_quantile: float) -> dict:
    margin_cut = float(train_df["q2_margin"].median())
    vol_cut = float(train_df["rev_volatility"].median())

    train_with_regime = train_df.copy()
    train_with_regime["regime"] = build_regime_label(train_with_regime, margin_cut=margin_cut, vol_cut=vol_cut)

    global_model = fit_rf(train_with_regime[FEATURES], train_with_regime[TARGET_DELTA].to_numpy(dtype=float), seed=seed)
    _, global_std = predict_with_uncertainty(global_model, train_with_regime[FEATURES])
    global_std_cut = float(np.quantile(global_std, confidence_quantile))

    regime_models = {}
    regime_std_cut = {}
    for regime_name, part in train_with_regime.groupby("regime"):
        if len(part) < min_regime_samples:
            continue
        model_r = fit_rf(part[FEATURES], part[TARGET_DELTA].to_numpy(dtype=float), seed=seed)
        _, std_r = predict_with_uncertainty(model_r, part[FEATURES])
        regime_models[regime_name] = model_r
        regime_std_cut[regime_name] = float(np.quantile(std_r, confidence_quantile))

    return {
        "margin_cut": margin_cut,
        "vol_cut": vol_cut,
        "global_model": global_model,
        "global_std_cut": global_std_cut,
        "regime_models": regime_models,
        "regime_std_cut": regime_std_cut,
    }


def predict_regime_bundle(bundle: dict, df_eval: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    eval_with_regime = df_eval.copy().reset_index(drop=True)
    eval_with_regime["regime"] = build_regime_label(
        eval_with_regime,
        margin_cut=bundle["margin_cut"],
        vol_cut=bundle["vol_cut"],
    )

    baseline_eps = eval_with_regime["q2_eps"].to_numpy(dtype=float)
    pred_eps = baseline_eps.copy()
    src_regime = np.array(["baseline_q2_fallback" for _ in range(len(eval_with_regime))], dtype=object)

    global_mean, global_std = predict_with_uncertainty(bundle["global_model"], eval_with_regime[FEATURES])
    global_ok = global_std <= bundle["global_std_cut"]
    pred_eps[global_ok] = baseline_eps[global_ok] + global_mean[global_ok]
    src_regime[global_ok] = "global"
    conf_std = global_std.copy()

    # regime 預測通過門檻時覆蓋 global
    for regime_name, model_r in bundle["regime_models"].items():
        mask_reg = eval_with_regime["regime"].to_numpy() == regime_name
        if not np.any(mask_reg):
            continue
        idx = np.where(mask_reg)[0]
        x_reg = eval_with_regime.loc[mask_reg, FEATURES]
        r_mean, r_std = predict_with_uncertainty(model_r, x_reg)
        r_ok = r_std <= bundle["regime_std_cut"][regime_name]
        if not np.any(r_ok):
            continue
        idx_ok = idx[r_ok]
        pred_eps[idx_ok] = baseline_eps[idx_ok] + r_mean[r_ok]
        src_regime[idx_ok] = "regime"
        conf_std[idx_ok] = r_std[r_ok]

    return pred_eps, src_regime, conf_std


def build_valuation_daily_frame(df_eval: pd.DataFrame, pred_eps: np.ndarray, model_version: str, source_file: str) -> pd.DataFrame:
    out = pd.DataFrame()
    out["date"] = df_eval["q3_date"] if "q3_date" in df_eval.columns else pd.Series([np.nan] * len(df_eval))
    out["symbol"] = df_eval["symbol"] if "symbol" in df_eval.columns else pd.Series([np.nan] * len(df_eval))
    out["close"] = df_eval["q3_close"] if "q3_close" in df_eval.columns else pd.Series([np.nan] * len(df_eval))
    out["volume"] = df_eval["q3_volume"] if "q3_volume" in df_eval.columns else pd.Series([np.nan] * len(df_eval))

    ttm_official = df_eval["ttm_eps_official"].to_numpy(dtype=float)
    target_eps = df_eval[TARGET].to_numpy(dtype=float)
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

    out["pced_file"] = source_file
    out["pced_row"] = np.arange(len(out))
    out["pced_col"] = "pred_rf_regime"
    out["model_version"] = model_version

    return out


def quality_check_and_report(df_val: pd.DataFrame, report_path: Path) -> None:
    checks = {}

    for col in [
        "date",
        "symbol",
        "close",
        "ttm_eps_official",
        "ttm_eps_forward",
        "pe_official",
        "pe_forward",
        "predict_target_price",
        "upside_pct",
    ]:
        if col in df_val.columns:
            checks[f"null_rate__{col}"] = float(df_val[col].isna().mean())

    numeric_cols = [c for c in df_val.columns if pd.api.types.is_numeric_dtype(df_val[c])]
    for col in numeric_cols:
        arr = df_val[col].to_numpy(dtype=float)
        checks[f"inf_rate__{col}"] = float(np.mean(np.isinf(arr)))

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

        bundle = train_regime_bundle(
            train_df=train_df,
            seed=args.seed,
            min_regime_samples=args.min_regime_samples,
            confidence_quantile=args.confidence_quantile,
        )

        y_true = test_df[TARGET].to_numpy(dtype=float)
        pred_eps_rf, pred_src, pred_std = predict_regime_bundle(bundle=bundle, df_eval=test_df)

        pred_eps_baseline_q2 = test_df["q2_eps"].to_numpy(dtype=float)
        pred_eps_baseline_median = np.full(len(test_df), float(train_df[TARGET].median()), dtype=float)

        model_predictions = [
            ("rf_regime", pred_eps_rf),
            ("baseline_q2_eps", pred_eps_baseline_q2),
            ("baseline_train_median", pred_eps_baseline_median),
        ]

        for model_name, pred_eps in model_predictions:
            metric_values = evaluate_metrics(test_df, y_true, pred_eps, args.eps_floor)
            row = {
                "version": "v7",
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

            if model_name == "rf_regime":
                row["source_ratio_regime"] = float(np.mean(pred_src == "regime"))
                row["source_ratio_global"] = float(np.mean(pred_src == "global"))
                row["source_ratio_baseline_fallback"] = float(np.mean(pred_src == "baseline_q2_fallback"))
                row["avg_prediction_std"] = float(np.mean(pred_std))

            fold_rows.append(row)

        keep_cols = [
            c
            for c in ["year", "symbol", "name", "q3_date", "q3_close", "q3_volume", "pe_current", "ttm_eps_official"]
            if c in test_df.columns
        ]
        pred_detail_df = test_df[keep_cols].copy()
        pred_detail_df["y_true"] = y_true
        pred_detail_df["pred_rf_regime"] = pred_eps_rf
        pred_detail_df["pred_source"] = pred_src
        pred_detail_df["pred_std"] = pred_std
        pred_detail_df["pred_baseline_q2_eps"] = pred_eps_baseline_q2
        pred_detail_df["pred_baseline_train_median"] = pred_eps_baseline_median
        pred_detail_df["fold"] = f"year_{test_year}"
        pred_rows.append(pred_detail_df)

        val_df = build_valuation_daily_frame(
            df_eval=test_df,
            pred_eps=pred_eps_rf,
            model_version="v7",
            source_file="analysis_codex/v7/results/predictions.csv",
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

    print("v7 backtest completed")
    print(f"- {fold_path}")
    print(f"- {pred_path}")
    print(f"- {valuation_path}")
    print(f"- {quality_path}")


if __name__ == "__main__":
    main()
