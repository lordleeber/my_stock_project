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
    "rev_yoy_m7_z",
    "rev_yoy_m8_z",
    "rev_mom_m8_m7_z",
    "margin_momentum",
    "q2_roe",
    "q2_debt_ratio",
    "q2_non_op_ratio",
]
Z_FEATURES = ["rev_yoy_m7_z", "rev_yoy_m8_z", "rev_mom_m8_m7_z"]
TARGET = "target_eps"
TARGET_DELTA = "delta_eps"

DATASET_PATH = Path(__file__).resolve().parent / "dataset.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest for analysis/v9_t2")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--winsor-quantile", type=float, default=0.01)
    parser.add_argument("--confidence-quantile", type=float, default=0.95)
    parser.add_argument("--feature-transform", type=str, choices=["zscore", "rank", "quantile"], default="zscore")
    parser.add_argument("--year-param-start", type=int, default=2025)
    parser.add_argument("--year-winsor-quantile", type=float, default=None)
    parser.add_argument("--year-confidence-quantile", type=float, default=None)
    parser.add_argument("--n-jobs", type=int, default=-1)
    parser.add_argument("--eps-floor", type=float, default=0.20)
    parser.add_argument("--min-ttm-eps", type=float, default=2.0)
    parser.add_argument("--min-volume-lots", type=float, default=500.0)
    return parser.parse_args()


def winsorize_train_test(train_df: pd.DataFrame, test_df: pd.DataFrame, cols: list[str], q: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    if q <= 0:
        return train_df, test_df
    tr = train_df.copy()
    te = test_df.copy()
    for c in cols:
        lo = float(tr[c].quantile(q))
        hi = float(tr[c].quantile(1.0 - q))
        tr[c] = tr[c].clip(lo, hi)
        te[c] = te[c].clip(lo, hi)
    return tr, te


def mae_or_nan(values: np.ndarray) -> float:
    valid = values[~np.isnan(values)]
    if len(valid) == 0:
        return float("nan")
    return float(np.mean(np.abs(valid)))


def percentile_rank(series: pd.Series, value: float) -> float:
    if series.empty or np.isnan(value):
        return float("nan")
    return float((series <= value).mean())


def predict_with_uncertainty(model: RandomForestRegressor, x_data: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    x_np = x_data.to_numpy(dtype=float)
    tree_preds = np.vstack([tree.predict(x_np) for tree in model.estimators_])
    return tree_preds.mean(axis=0), tree_preds.std(axis=0)


def add_cross_section_transforms(df: pd.DataFrame, z_cols: list[str]) -> None:
    group_cols = ["year", "industry"] if "industry" in df.columns else ["year"]
    for z_col in z_cols:
        rank_col = z_col.replace("_z", "_rank")
        quantile_col = z_col.replace("_z", "_quantile")

        ranks = df.groupby(group_cols)[z_col].rank(method="average", pct=True).fillna(0.5)
        df[rank_col] = ranks
        # 分箱後讓模型看到更穩定的相對位置訊號
        df[quantile_col] = np.ceil(ranks * 10.0).clip(1.0, 10.0) / 10.0


def resolve_features(transform: str) -> list[str]:
    if transform == "zscore":
        return FEATURES
    suffix = "_rank" if transform == "rank" else "_quantile"
    return [f.replace("_z", suffix) if f in Z_FEATURES else f for f in FEATURES]


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

    mask_off = (~np.isnan(close)) & (np.abs(ttm_official) > 1e-9)
    mask_fwd = (~np.isnan(close)) & (np.abs(ttm_forward) > 1e-9)
    pe_official[mask_off] = close[mask_off] / ttm_official[mask_off]
    pe_forward[mask_fwd] = close[mask_fwd] / ttm_forward[mask_fwd]

    out["pe_official"] = pe_official
    out["pe_forward"] = pe_forward
    out["pe_percentile_official"] = [percentile_rank(pd.Series(pe_official).dropna(), v) for v in pe_official]
    out["pe_percentile_forward"] = [percentile_rank(pd.Series(pe_forward).dropna(), v) for v in pe_forward]

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
        ok = np.abs(q2_eps) > 1e-9
        roe_forward[ok] = (pred_eps[ok] / q2_eps[ok]) * q2_roe[ok]
    out["roe_forward"] = roe_forward

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
    for col in [c for c in df_val.columns if pd.api.types.is_numeric_dtype(df_val[c])]:
        checks[f"inf_rate__{col}"] = float(np.mean(np.isinf(df_val[col].to_numpy(dtype=float))))
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
    true_ok = np.abs(y_true) >= eps_floor
    pred_ok = np.abs(y_pred) >= eps_floor
    true_forward_pe[valid_price & true_ok] = close[valid_price & true_ok] / y_true[valid_price & true_ok]
    pred_forward_pe[valid_price & pred_ok] = close[valid_price & pred_ok] / y_pred[valid_price & pred_ok]

    true_target_price = np.full(len(df_eval), np.nan)
    pred_target_price = np.full(len(df_eval), np.nan)
    true_target_price[valid_pe] = y_true[valid_pe] * pe_current[valid_pe]
    pred_target_price[valid_pe] = y_pred[valid_pe] * pe_current[valid_pe]

    true_upside = np.full(len(df_eval), np.nan)
    pred_upside = np.full(len(df_eval), np.nan)
    mask_up = valid_price & (~np.isnan(true_target_price)) & (~np.isnan(pred_target_price))
    true_upside[mask_up] = (true_target_price[mask_up] / close[mask_up] - 1.0) * 100.0
    pred_upside[mask_up] = (pred_target_price[mask_up] / close[mask_up] - 1.0) * 100.0

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

    df = pd.read_csv(DATASET_PATH).replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[TARGET, TARGET_DELTA, "year", "q2_eps"])
    for c in FEATURES:
        df[c] = df[c].fillna(0)

    years = sorted(df["year"].astype(int).unique().tolist())
    fold_rows, pred_rows, valuation_rows = [], [], []

    for test_year in years[1:]:
        train_raw = df[df["year"].astype(int) < test_year].copy()
        test_raw = df[df["year"].astype(int) == test_year].copy()
        if train_raw.empty or test_raw.empty:
            continue

        effective_winsor_q = args.winsor_quantile
        if args.year_winsor_quantile is not None and test_year >= args.year_param_start:
            effective_winsor_q = args.year_winsor_quantile

        effective_conf_q = args.confidence_quantile
        if args.year_confidence_quantile is not None and test_year >= args.year_param_start:
            effective_conf_q = args.year_confidence_quantile

        winsor_cols = [c for c in FEATURES if c != "q2_eps"] + [TARGET_DELTA]
        train_df, test_df = winsorize_train_test(train_raw, test_raw, winsor_cols, effective_winsor_q)
        add_cross_section_transforms(train_df, Z_FEATURES)
        add_cross_section_transforms(test_df, Z_FEATURES)
        use_features = resolve_features(args.feature_transform)

        model = RandomForestRegressor(n_estimators=400, max_depth=12, random_state=args.seed, criterion="absolute_error", n_jobs=args.n_jobs)
        model.fit(train_df[use_features], train_df[TARGET_DELTA])

        y_true = test_df[TARGET].to_numpy(dtype=float)
        pred_delta_raw, pred_delta_std = predict_with_uncertainty(model, test_df[use_features])
        _, pred_delta_train_std = predict_with_uncertainty(model, train_df[use_features])
        threshold = float(np.quantile(pred_delta_train_std, effective_conf_q))
        pred_delta = np.where(pred_delta_std > threshold, 0.0, pred_delta_raw)
        pred_eps_rf = test_df["q2_eps"].to_numpy(dtype=float) + pred_delta

        pred_eps_q2 = test_df["q2_eps"].to_numpy(dtype=float)
        pred_eps_med = np.full(len(test_df), float(train_df[TARGET].median()), dtype=float)

        for model_name, pred in [("rf_delta", pred_eps_rf), ("baseline_q2_eps", pred_eps_q2), ("baseline_train_median", pred_eps_med)]:
            m = evaluate_metrics(test_df, y_true, pred, args.eps_floor)
            fold_rows.append(
                {
                    "version": "v9_t2",
                    "protocol": "expanding_by_year",
                    "fold": f"year_{test_year}",
                    "model": model_name,
                    "feature_transform": args.feature_transform,
                    "effective_winsor_q": effective_winsor_q,
                    "effective_confidence_q": effective_conf_q,
                    **m,
                    "n_train": len(train_df),
                    "n_test": len(test_df),
                }
            )

        keep_cols = [c for c in ["year", "symbol", "name", "industry", "feature_cutoff_date", "q3_date", "q3_close", "q3_volume", "pe_current", "ttm_eps_official"] if c in test_df.columns]
        tmp = test_df[keep_cols].copy()
        tmp["y_true"] = y_true
        tmp["pred_rf_delta"] = pred_eps_rf
        tmp["pred_delta_std"] = pred_delta_std
        tmp["confidence_threshold"] = threshold
        tmp["pred_baseline_q2_eps"] = pred_eps_q2
        tmp["pred_baseline_train_median"] = pred_eps_med
        tmp["feature_transform"] = args.feature_transform
        tmp["effective_winsor_q"] = effective_winsor_q
        tmp["effective_confidence_q"] = effective_conf_q
        tmp["fold"] = f"year_{test_year}"
        pred_rows.append(tmp)

        val = build_valuation_daily_frame(test_df, pred_eps_rf, f"v9_t2_{args.feature_transform}", "analysis_codex/v9/t2/results/predictions.csv")
        val["fold"] = f"year_{test_year}"
        valuation_rows.append(val)

    fold_df = pd.DataFrame(fold_rows)
    pred_df = pd.concat(pred_rows, ignore_index=True) if pred_rows else pd.DataFrame()
    val_df = pd.concat(valuation_rows, ignore_index=True) if valuation_rows else pd.DataFrame()

    if not val_df.empty:
        ttm_ok = val_df["ttm_eps_forward"] >= float(args.min_ttm_eps)
        vol_ok = (val_df["volume"] / 1000.0) >= float(args.min_volume_lots)
        val_df = val_df[ttm_ok & vol_ok].copy()

    for frame, nd in [(fold_df, 2), (pred_df, 2), (val_df, 4)]:
        num_cols = frame.select_dtypes(include=[np.number]).columns.tolist()
        if num_cols:
            frame[num_cols] = frame[num_cols].round(nd)

    fold_path = RESULTS_DIR / "backtest_by_fold.csv"
    pred_path = RESULTS_DIR / "predictions.csv"
    val_path = RESULTS_DIR / "valuation_daily_preview.csv"
    q_path = RESULTS_DIR / "valuation_quality_report.json"

    fold_df.to_csv(fold_path, index=False)
    pred_df.to_csv(pred_path, index=False)
    val_df.to_csv(val_path, index=False)
    quality_check_and_report(val_df, q_path)

    print("v9_t2 backtest completed")
    print(f"- {fold_path}")


if __name__ == "__main__":
    main()
