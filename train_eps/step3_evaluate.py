import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from shared_config import load_shared_config
from sklearn.metrics import mean_absolute_error

TARGET = "target_eps"
TARGET_DELTA = "delta_eps"
EVAL_EXCLUDE_COLUMNS = {
    "symbol",
    "name",
    "industry",
    "year",
    "anchor_quarter",
    TARGET,
    TARGET_DELTA,
}

BASE_DIR = Path(__file__).resolve().parent
FEATURE_TRANSFORM = "quantile"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shared evaluate for train_eps/output/<year>/<month>"
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="01~12")
    return parser.parse_args()


def resolve_month_context(year: int, month: str) -> tuple[Path, Path, Path]:
    month_name = str(month).zfill(2)
    if month_name < "01" or month_name > "12":
        raise ValueError("--month 必須是 01~12")
    dataset_path = (
        Path.cwd()
        / "train_eps"
        / "output"
        / str(year)
        / month_name
        / "dataset_evaluate.csv"
    ).resolve()
    results_dir = (Path.cwd() / "models_eps" / str(year) / month_name).resolve()
    return dataset_path, results_dir


def winsorize_train_test(
    train_df: pd.DataFrame, test_df: pd.DataFrame, cols: list[str], q: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
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


def build_lgb_regressor(
    args: argparse.Namespace, objective: str = "mae", alpha: float | None = None
) -> LGBMRegressor:
    kwargs: dict[str, float | int | str] = {
        "objective": objective,
        "n_estimators": args.n_estimators,
        "learning_rate": args.learning_rate,
        "num_leaves": args.num_leaves,
        "subsample": args.subsample,
        "colsample_bytree": args.colsample_bytree,
        "reg_alpha": args.reg_alpha,
        "reg_lambda": args.reg_lambda,
        "random_state": args.seed,
        "n_jobs": args.n_jobs,
    }
    if objective == "quantile":
        kwargs["alpha"] = float(alpha if alpha is not None else 0.5)
    return LGBMRegressor(**kwargs)


def infer_feature_set(df: pd.DataFrame) -> list[str]:
    feature_cols = [c for c in df.columns if c not in EVAL_EXCLUDE_COLUMNS]
    if "anchor_eps" not in feature_cols:
        raise ValueError("dataset_evaluate.csv 必須包含 anchor_eps 欄位")
    if not feature_cols:
        raise ValueError("沒有可用特徵欄位，請檢查 dataset_evaluate.csv")
    quantile_features = [c for c in feature_cols if c.endswith("_quantile")]
    if not quantile_features:
        raise ValueError(
            "dataset_evaluate.csv 缺少 *_quantile 特徵。請先執行新版 prepare_data.py。"
        )
    return feature_cols


def evaluate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    abs_err = np.abs(y_true - y_pred)
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "p90_ae": float(np.quantile(abs_err, 0.9)),
    }


def interval_metrics(y_true: np.ndarray, y_low: np.ndarray, y_high: np.ndarray) -> dict:
    width = y_high - y_low
    valid = (~np.isnan(y_true)) & (~np.isnan(y_low)) & (~np.isnan(y_high))
    if not np.any(valid):
        return {"interval_coverage": float("nan"), "interval_avg_width": float("nan")}
    in_interval = (y_true[valid] >= y_low[valid]) & (y_true[valid] <= y_high[valid])
    return {
        "interval_coverage": float(np.mean(in_interval)),
        "interval_avg_width": float(np.mean(width[valid])),
    }


def calibrate_interval_scale(
    y_true: np.ndarray,
    y_mid: np.ndarray,
    y_low: np.ndarray,
    y_high: np.ndarray,
    target_coverage: float | None,
    min_samples: int,
    min_scale: float,
    max_scale: float,
) -> float:
    if target_coverage is None:
        return 1.0
    if target_coverage <= 0.0 or target_coverage >= 1.0:
        return 1.0
    if len(y_true) < min_samples:
        return 1.0

    half_width = (y_high - y_low) / 2.0
    valid = (~np.isnan(y_true)) & (~np.isnan(y_mid)) & (~np.isnan(half_width))
    if not np.any(valid):
        return 1.0

    half_width_valid = np.clip(half_width[valid], 1e-6, None)
    norm_err = np.abs(y_true[valid] - y_mid[valid]) / half_width_valid
    if len(norm_err) < min_samples:
        return 1.0

    scale = float(np.quantile(norm_err, target_coverage))
    return float(np.clip(scale, min_scale, max_scale))


def calibrate_interval_scale_by_regime(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    y_true_train: np.ndarray,
    y_mid_train: np.ndarray,
    y_low_train: np.ndarray,
    y_high_train: np.ndarray,
    pred_std_train: np.ndarray,
    pred_std_test: np.ndarray,
    target_coverage: float | None,
    min_samples: int,
    min_scale: float,
    max_scale: float,
) -> tuple[np.ndarray, str, float]:
    global_scale = calibrate_interval_scale(
        y_true_train,
        y_mid_train,
        y_low_train,
        y_high_train,
        target_coverage,
        min_samples,
        min_scale,
        max_scale,
    )
    if target_coverage is None:
        return (
            np.full(len(test_df), global_scale, dtype=float),
            "regime_disabled_target_none",
            global_scale,
        )

    train_reg = train_df.copy()
    test_reg = test_df.copy()
    train_reg["industry_key"] = (
        train_reg.get("industry", pd.Series(index=train_reg.index))
        .fillna("unknown")
        .astype(str)
    )
    test_reg["industry_key"] = (
        test_reg.get("industry", pd.Series(index=test_reg.index))
        .fillna("unknown")
        .astype(str)
    )

    q1 = float(np.quantile(pred_std_train, 0.33))
    q2 = float(np.quantile(pred_std_train, 0.66))
    train_reg["unc_bucket"] = np.where(
        pred_std_train <= q1, "low", np.where(pred_std_train <= q2, "mid", "high")
    )
    test_reg["unc_bucket"] = np.where(
        pred_std_test <= q1, "low", np.where(pred_std_test <= q2, "mid", "high")
    )
    train_reg["regime_key"] = train_reg["industry_key"] + "__" + train_reg["unc_bucket"]
    test_reg["regime_key"] = test_reg["industry_key"] + "__" + test_reg["unc_bucket"]

    scales: dict[str, float] = {}
    for key, idx in train_reg.groupby("regime_key").groups.items():
        idx_arr = np.array(list(idx), dtype=int)
        if len(idx_arr) < min_samples:
            continue
        scales[key] = calibrate_interval_scale(
            y_true_train[idx_arr],
            y_mid_train[idx_arr],
            y_low_train[idx_arr],
            y_high_train[idx_arr],
            target_coverage,
            min_samples,
            min_scale,
            max_scale,
        )

    if len(scales) == 0:
        raise RuntimeError(
            "Calibration failed: no valid regime groups for regime mode."
        )

    out_scale = np.full(len(test_df), global_scale, dtype=float)
    for i, key in enumerate(test_reg["regime_key"].astype(str).tolist()):
        if key in scales:
            out_scale[i] = scales[key]

    return out_scale, f"regime_groups={len(scales)}", global_scale


def calibrate_interval_scale_nonlinear(
    y_true_train: np.ndarray,
    y_mid_train: np.ndarray,
    y_low_train: np.ndarray,
    y_high_train: np.ndarray,
    pred_std_train: np.ndarray,
    pred_std_test: np.ndarray,
    target_coverage: float | None,
    min_samples: int,
    min_scale: float,
    max_scale: float,
    n_bins: int,
    min_bin_samples: int,
) -> tuple[np.ndarray, str, float]:
    global_scale = calibrate_interval_scale(
        y_true_train,
        y_mid_train,
        y_low_train,
        y_high_train,
        target_coverage,
        min_samples,
        min_scale,
        max_scale,
    )
    if target_coverage is None:
        return (
            np.full(len(pred_std_test), global_scale, dtype=float),
            "nonlinear_disabled_target_none",
            global_scale,
        )

    if len(y_true_train) < max(min_samples, min_bin_samples * 2):
        raise RuntimeError(
            "Calibration failed: nonlinear mode requires more training samples."
        )

    half_width = (y_high_train - y_low_train) / 2.0
    valid = (
        (~np.isnan(y_true_train))
        & (~np.isnan(y_mid_train))
        & (~np.isnan(half_width))
        & (~np.isnan(pred_std_train))
    )
    if int(np.sum(valid)) < max(min_samples, min_bin_samples * 2):
        raise RuntimeError(
            "Calibration failed: nonlinear mode has insufficient valid training rows."
        )

    std_v = pred_std_train[valid]
    y_true_v = y_true_train[valid]
    y_mid_v = y_mid_train[valid]
    hw_v = np.clip(half_width[valid], 1e-6, None)
    ratio_v = np.abs(y_true_v - y_mid_v) / hw_v

    n_bins = max(3, int(n_bins))
    quantiles = np.linspace(0.0, 1.0, n_bins + 1)
    edges = np.quantile(std_v, quantiles)
    edges = np.unique(edges)
    if len(edges) < 3:
        raise RuntimeError(
            "Calibration failed: nonlinear mode has degenerated uncertainty distribution."
        )

    bin_scales = []
    bin_left = []
    bin_right = []
    for i in range(len(edges) - 1):
        lo = float(edges[i])
        hi = float(edges[i + 1])
        if i == len(edges) - 2:
            mask = (std_v >= lo) & (std_v <= hi)
        else:
            mask = (std_v >= lo) & (std_v < hi)
        if int(np.sum(mask)) < min_bin_samples:
            continue
        s = float(np.quantile(ratio_v[mask], target_coverage))
        s = float(np.clip(s, min_scale, max_scale))
        bin_left.append(lo)
        bin_right.append(hi)
        bin_scales.append(s)

    if len(bin_scales) < 2:
        raise RuntimeError(
            "Calibration failed: nonlinear mode has insufficient populated bins."
        )

    bin_scales = np.maximum.accumulate(np.array(bin_scales, dtype=float))

    out_scale = np.full(len(pred_std_test), global_scale, dtype=float)
    for i, std_val in enumerate(pred_std_test):
        if np.isnan(std_val):
            continue
        hit = False
        for j in range(len(bin_scales)):
            lo = bin_left[j]
            hi = bin_right[j]
            if j == len(bin_scales) - 1:
                if std_val >= lo and std_val <= hi:
                    out_scale[i] = bin_scales[j]
                    hit = True
                    break
            else:
                if std_val >= lo and std_val < hi:
                    out_scale[i] = bin_scales[j]
                    hit = True
                    break
        if not hit:
            if std_val < bin_left[0]:
                out_scale[i] = bin_scales[0]
            elif std_val > bin_right[-1]:
                out_scale[i] = bin_scales[-1]

    return out_scale, f"nonlinear_bins={len(bin_scales)}", global_scale


def main() -> None:
    args = parse_args()
    dataset_path, results_dir = resolve_month_context(args.year, args.month)
    results_dir.mkdir(parents=True, exist_ok=True)
    config, _ = load_shared_config()
    common_cfg = config["common"]
    lgb_cfg = config["lightgbm-train"]
    eval_cfg = config["lightgbm-evaluate"]
    args.seed = int(common_cfg["seed"])
    args.winsor_quantile = float(common_cfg["winsor_quantile"])
    args.n_jobs = int(common_cfg["n_jobs"])
    args.n_estimators = int(lgb_cfg["n_estimators"])
    args.learning_rate = float(lgb_cfg["learning_rate"])
    args.num_leaves = int(lgb_cfg["num_leaves"])
    args.subsample = float(lgb_cfg["subsample"])
    args.colsample_bytree = float(lgb_cfg["colsample_bytree"])
    args.reg_alpha = float(lgb_cfg["reg_alpha"])
    args.reg_lambda = float(lgb_cfg["reg_lambda"])
    args.confidence_quantile = float(eval_cfg["confidence_quantile"])
    args.interval_method = str(eval_cfg["interval_method"])
    args.interval_low_quantile = float(eval_cfg["interval_low_quantile"])
    args.interval_high_quantile = float(eval_cfg["interval_high_quantile"])
    args.target_coverage = (
        None
        if eval_cfg["target_coverage"] is None
        else float(eval_cfg["target_coverage"])
    )
    args.calibration_mode = str(eval_cfg["calibration_mode"])
    args.min_calib_samples = int(eval_cfg["min_calib_samples"])
    args.min_calib_scale = float(eval_cfg["min_calib_scale"])
    args.max_calib_scale = float(eval_cfg["max_calib_scale"])
    args.nonlinear_bins = int(eval_cfg["nonlinear_bins"])
    args.nonlinear_min_bin_samples = int(eval_cfg["nonlinear_min_bin_samples"])

    df = pd.read_csv(dataset_path).replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[TARGET, TARGET_DELTA, "year", "anchor_eps"])
    feature_cols = infer_feature_set(df)

    years = sorted(df["year"].astype(int).unique().tolist())
    fold_rows = []

    for test_year in years[1:]:
        train_raw = df[df["year"].astype(int) < test_year].copy()
        test_raw = df[df["year"].astype(int) == test_year].copy()
        if train_raw.empty or test_raw.empty:
            continue

        effective_winsor_q = args.winsor_quantile
        effective_conf_q = args.confidence_quantile

        winsor_cols = [c for c in feature_cols if c != "anchor_eps"] + [TARGET_DELTA]
        train_df, test_df = winsorize_train_test(
            train_raw, test_raw, winsor_cols, effective_winsor_q
        )
        # prepare_data 已完成特徵轉換，evaluate 只讀取最終特徵
        use_features = feature_cols

        model = build_lgb_regressor(args, objective="mae")
        model.fit(train_df[use_features], train_df[TARGET_DELTA])

        y_true = test_df[TARGET].to_numpy(dtype=float)
        pred_delta_raw = model.predict(test_df[use_features])
        train_delta_raw = model.predict(train_df[use_features])

        q_low_model = build_lgb_regressor(
            args, objective="quantile", alpha=float(args.interval_low_quantile)
        )
        q_high_model = build_lgb_regressor(
            args, objective="quantile", alpha=float(args.interval_high_quantile)
        )
        q_low_model.fit(train_df[use_features], train_df[TARGET_DELTA])
        q_high_model.fit(train_df[use_features], train_df[TARGET_DELTA])

        pred_delta_low = q_low_model.predict(test_df[use_features])
        pred_delta_high = q_high_model.predict(test_df[use_features])
        train_delta_low = q_low_model.predict(train_df[use_features])
        train_delta_high = q_high_model.predict(train_df[use_features])

        # 用 quantile 區間寬度當作不確定性代理，沿用原有 confidence gating 機制。
        pred_delta_std = np.maximum(0.0, (pred_delta_high - pred_delta_low) / 2.0)
        pred_delta_train_std = np.maximum(
            0.0, (train_delta_high - train_delta_low) / 2.0
        )
        threshold = float(np.quantile(pred_delta_train_std, effective_conf_q))
        pred_delta = np.where(pred_delta_std > threshold, 0.0, pred_delta_raw)

        pred_lo = np.minimum(pred_delta_low, pred_delta_high)
        pred_hi = np.maximum(pred_delta_low, pred_delta_high)
        pred_delta_low = np.minimum(pred_lo, pred_delta_raw)
        pred_delta_high = np.maximum(pred_hi, pred_delta_raw)
        train_lo = np.minimum(train_delta_low, train_delta_high)
        train_hi = np.maximum(train_delta_low, train_delta_high)
        train_delta_low = np.minimum(train_lo, train_delta_raw)
        train_delta_high = np.maximum(train_hi, train_delta_raw)

        pred_eps_from_delta = test_df["anchor_eps"].to_numpy(dtype=float) + pred_delta
        pred_eps_low = test_df["anchor_eps"].to_numpy(dtype=float) + pred_delta_low
        pred_eps_high = test_df["anchor_eps"].to_numpy(dtype=float) + pred_delta_high

        train_delta_mid = np.where(
            pred_delta_train_std > threshold, 0.0, train_delta_raw
        )
        train_eps_mid = train_df["anchor_eps"].to_numpy(dtype=float) + train_delta_mid
        train_eps_low = train_df["anchor_eps"].to_numpy(dtype=float) + train_delta_low
        train_eps_high = train_df["anchor_eps"].to_numpy(dtype=float) + train_delta_high

        calib_source = "global"
        per_row_scale = np.full(len(test_df), 1.0, dtype=float)
        if args.calibration_mode == "latest_year":
            latest_year = int(train_df["year"].astype(int).max())
            latest_mask = train_df["year"].astype(int).to_numpy() == latest_year
            if int(np.sum(latest_mask)) >= args.min_calib_samples:
                scale_value = calibrate_interval_scale(
                    train_df.loc[latest_mask, TARGET].to_numpy(dtype=float),
                    train_eps_mid[latest_mask],
                    train_eps_low[latest_mask],
                    train_eps_high[latest_mask],
                    args.target_coverage,
                    args.min_calib_samples,
                    args.min_calib_scale,
                    args.max_calib_scale,
                )
                calib_source = f"latest_year_{latest_year}"
            else:
                raise RuntimeError(
                    f"Calibration failed: latest_year mode requires >= {args.min_calib_samples} rows in latest year "
                    f"(latest_year={latest_year}, rows={int(np.sum(latest_mask))})."
                )
            per_row_scale = np.full(len(test_df), scale_value, dtype=float)
        elif args.calibration_mode == "regime":
            # 第三項是 global fallback scale，已被吸收到 per_row_scale 內，外部不需要再用。
            per_row_scale, calib_source, _ = calibrate_interval_scale_by_regime(
                train_df=train_df,
                test_df=test_df,
                y_true_train=train_df[TARGET].to_numpy(dtype=float),
                y_mid_train=train_eps_mid,
                y_low_train=train_eps_low,
                y_high_train=train_eps_high,
                pred_std_train=pred_delta_train_std,
                pred_std_test=pred_delta_std,
                target_coverage=args.target_coverage,
                min_samples=args.min_calib_samples,
                min_scale=args.min_calib_scale,
                max_scale=args.max_calib_scale,
            )
        elif args.calibration_mode == "nonlinear":
            # 第三項是 global fallback scale，已被吸收到 per_row_scale 內，外部不需要再用。
            per_row_scale, calib_source, _ = calibrate_interval_scale_nonlinear(
                y_true_train=train_df[TARGET].to_numpy(dtype=float),
                y_mid_train=train_eps_mid,
                y_low_train=train_eps_low,
                y_high_train=train_eps_high,
                pred_std_train=pred_delta_train_std,
                pred_std_test=pred_delta_std,
                target_coverage=args.target_coverage,
                min_samples=args.min_calib_samples,
                min_scale=args.min_calib_scale,
                max_scale=args.max_calib_scale,
                n_bins=args.nonlinear_bins,
                min_bin_samples=args.nonlinear_min_bin_samples,
            )
        elif args.calibration_mode == "global":
            scale_value = calibrate_interval_scale(
                train_df[TARGET].to_numpy(dtype=float),
                train_eps_mid,
                train_eps_low,
                train_eps_high,
                args.target_coverage,
                args.min_calib_samples,
                args.min_calib_scale,
                args.max_calib_scale,
            )
            per_row_scale = np.full(len(test_df), scale_value, dtype=float)
        else:
            raise ValueError(
                "Invalid calibration_mode. Allowed values: latest_year, regime, nonlinear, global."
            )

        pred_half_width = (pred_eps_high - pred_eps_low) / 2.0
        pred_eps_low = pred_eps_from_delta - pred_half_width * per_row_scale
        pred_eps_high = pred_eps_from_delta + pred_half_width * per_row_scale

        pred_eps_anchor = test_df["anchor_eps"].to_numpy(dtype=float)
        pred_eps_med = np.full(
            len(test_df), float(train_df[TARGET].median()), dtype=float
        )

        for model_name, pred in [
            ("lgb_delta", pred_eps_from_delta),
            ("baseline_anchor_eps", pred_eps_anchor),
            ("baseline_train_median", pred_eps_med),
        ]:
            m = evaluate_metrics(y_true, pred)
            row = {
                "protocol": "expanding_by_year",
                "fold": f"year_{test_year}",
                "model": model_name,
                "feature_transform": FEATURE_TRANSFORM,
                "interval_method": args.interval_method,
                "effective_winsor_q": effective_winsor_q,
                "effective_confidence_q": effective_conf_q,
                "target_coverage": args.target_coverage
                if args.target_coverage is not None
                else np.nan,
                "calibration_mode": args.calibration_mode,
                "calibration_source": calib_source,
                "interval_scale": float(np.mean(per_row_scale)),
                **m,
                "n_train": len(train_df),
                "n_test": len(test_df),
            }
            if model_name == "lgb_delta":
                row.update(interval_metrics(y_true, pred_eps_low, pred_eps_high))
            fold_rows.append(row)

    fold_df = pd.DataFrame(fold_rows)

    num_cols = fold_df.select_dtypes(include=[np.number]).columns.tolist()
    if num_cols:
        fold_df[num_cols] = fold_df[num_cols].round(2)

    fold_path = results_dir / "evaluate_by_fold.json"
    fold_df.to_json(fold_path, orient="records", force_ascii=False, indent=2)

    print("evaluate completed")
    print(f"- {fold_path}")


if __name__ == "__main__":
    main()
