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

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = BASE_DIR / "dataset.csv"
DEFAULT_MODEL = BASE_DIR / "model.pkl"
DEFAULT_METRICS = BASE_DIR / "train_metrics.json"
DEFAULT_IMPORTANCE = BASE_DIR / "feature_importance.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train v7 regime-aware model for analysis_codex.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model-out", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--importance-out", type=Path, default=DEFAULT_IMPORTANCE)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-regime-samples", type=int, default=120)
    parser.add_argument("--confidence-quantile", type=float, default=0.95)
    return parser.parse_args()


def build_regime_label(df: pd.DataFrame, margin_cut: float, vol_cut: float) -> pd.Series:
    # 用「獲利能力 + 營收波動」把樣本切成 4 個 regime
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
    # 利用樹之間的分歧（std）當成低信心判斷依據
    x_np = x_data.to_numpy(dtype=float) if isinstance(x_data, pd.DataFrame) else np.asarray(x_data, dtype=float)
    tree_preds = np.vstack([tree.predict(x_np) for tree in model.estimators_])
    pred_mean = tree_preds.mean(axis=0)
    pred_std = tree_preds.std(axis=0)
    return pred_mean, pred_std


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.dataset).reset_index(drop=True)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[TARGET, TARGET_DELTA])

    for feature_name in FEATURES:
        df[feature_name] = df[feature_name].fillna(0)

    margin_cut = float(df["q2_margin"].median())
    vol_cut = float(df["rev_volatility"].median())
    df["regime"] = build_regime_label(df, margin_cut=margin_cut, vol_cut=vol_cut)

    x_all = df[FEATURES]
    y_delta = df[TARGET_DELTA].astype(float).to_numpy()

    global_model = fit_rf(x_all, y_delta, seed=args.seed)
    global_pred_delta, global_std = predict_with_uncertainty(global_model, x_all)
    global_std_cut = float(np.quantile(global_std, args.confidence_quantile))

    # regime 子模型：只有樣本夠多才訓練，避免小樣本過擬合
    regime_models: dict[str, RandomForestRegressor] = {}
    regime_std_cut: dict[str, float] = {}

    for regime_name, part in df.groupby("regime"):
        if len(part) < args.min_regime_samples:
            continue
        model_r = fit_rf(part[FEATURES], part[TARGET_DELTA].astype(float).to_numpy(), seed=args.seed)
        _, std_r = predict_with_uncertainty(model_r, part[FEATURES])
        regime_models[regime_name] = model_r
        regime_std_cut[regime_name] = float(np.quantile(std_r, args.confidence_quantile))

    baseline_eps = df["q2_eps"].astype(float).to_numpy()
    pred_eps = baseline_eps.copy()
    source_tag = np.array(["baseline_q2_fallback" for _ in range(len(df))], dtype=object)

    global_mean, global_std_eval = predict_with_uncertainty(global_model, x_all)
    global_ok = global_std_eval <= global_std_cut
    pred_eps[global_ok] = baseline_eps[global_ok] + global_mean[global_ok]
    source_tag[global_ok] = "global"

    # regime 預測通過信心門檻時，覆蓋 global 結果
    for regime_name, model_r in regime_models.items():
        mask_reg = df["regime"].to_numpy() == regime_name
        if not np.any(mask_reg):
            continue
        idx = np.where(mask_reg)[0]
        x_reg = df.loc[mask_reg, FEATURES]
        r_mean, r_std = predict_with_uncertainty(model_r, x_reg)
        r_ok = r_std <= regime_std_cut[regime_name]
        if not np.any(r_ok):
            continue
        idx_ok = idx[r_ok]
        pred_eps[idx_ok] = baseline_eps[idx_ok] + r_mean[r_ok]
        source_tag[idx_ok] = "regime"

    y_true = df[TARGET].astype(float).to_numpy()

    metrics = {
        "n_rows": int(len(df)),
        "main_metric": "mae",
        "train_mae_rf_regime": float(mean_absolute_error(y_true, pred_eps)),
        "train_mae_baseline_q2_eps": float(mean_absolute_error(y_true, baseline_eps)),
        "global_confidence_std_cut": global_std_cut,
        "confidence_quantile": float(args.confidence_quantile),
        "min_regime_samples": int(args.min_regime_samples),
        "regime_models": sorted(list(regime_models.keys())),
        "source_ratio_regime": float(np.mean(source_tag == "regime")),
        "source_ratio_global": float(np.mean(source_tag == "global")),
        "source_ratio_baseline_fallback": float(np.mean(source_tag == "baseline_q2_fallback")),
    }

    importance_rows = [
        {
            "model": "global",
            "feature": feature_name,
            "importance": float(imp),
        }
        for feature_name, imp in zip(FEATURES, global_model.feature_importances_)
    ]

    for regime_name, model_r in regime_models.items():
        for feature_name, imp in zip(FEATURES, model_r.feature_importances_):
            importance_rows.append(
                {
                    "model": f"regime::{regime_name}",
                    "feature": feature_name,
                    "importance": float(imp),
                }
            )

    importance_df = pd.DataFrame(importance_rows).sort_values(["model", "importance"], ascending=[True, False])

    bundle = {
        "version": "v7",
        "feature_names": FEATURES,
        "target_name": TARGET,
        "target_delta_name": TARGET_DELTA,
        "margin_cut": margin_cut,
        "vol_cut": vol_cut,
        "global_std_cut": global_std_cut,
        "confidence_quantile": float(args.confidence_quantile),
        "min_regime_samples": int(args.min_regime_samples),
        "global_model": global_model,
        "regime_models": regime_models,
        "regime_std_cut": regime_std_cut,
    }

    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.model_out, "wb") as model_file:
        pickle.dump(bundle, model_file)
    args.metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    importance_df.to_csv(args.importance_out, index=False)

    print("v7 train completed")
    print(f"- dataset: {args.dataset}")
    print(f"- model: {args.model_out}")
    print(f"- metrics: {args.metrics_out}")
    print(f"- feature importance: {args.importance_out}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
