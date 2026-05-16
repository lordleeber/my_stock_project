import argparse
import json
import pickle
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from shared_config import load_shared_config
from sklearn.metrics import mean_absolute_error

TARGET = "target_eps"
TARGET_DELTA = "delta_eps"
EXCLUDE_COLUMNS = {"year", "anchor_quarter", TARGET, TARGET_DELTA}

BASE_DIR = Path(__file__).resolve().parent

FEATURE_CHT_MAP = {
    "anchor_eps": "錨點季度每股盈餘",
    "ly_target_eps": "去年同目標季度每股盈餘",
    "anchor_yoy_eps": "錨點季度每股盈餘年增率",
    "anchor_margin": "錨點季度淨利率",
    "anchor_ocf_ratio": "錨點季度營業現金流對淨利比",
    "anchor_re_ratio": "錨點季度保留盈餘對資本比",
    "margin_momentum": "毛利動能（錨點季度-前一季度）",
    "anchor_roe": "錨點季度股東權益報酬率",
    "anchor_debt_ratio": "錨點季度負債比率",
    "anchor_non_op_ratio": "錨點季度業外損益占稅前淨利比",
    "ly_seasonality": "去年季節性（目標季度/錨點季度 EPS）",
    "xbrl_gross_margin_q": "XBRL單季毛利率",
    "xbrl_op_margin_q": "XBRL單季營業利益率",
    "xbrl_rd_ratio_q": "XBRL單季研發費用率",
    "xbrl_tax_rate_q": "XBRL單季有效稅率",
    "xbrl_current_ratio": "XBRL流動比率",
    "xbrl_cash_to_assets": "XBRL現金資產比",
    "xbrl_cfo_to_ni_q": "XBRL單季營運現金流對淨利比",
    "xbrl_capex_to_revenue_q": "XBRL單季資本支出對營收比",
}


def feature_cht_name(feature: str) -> str | None:
    if feature in FEATURE_CHT_MAP:
        return FEATURE_CHT_MAP[feature]
    m = re.fullmatch(r"rev_yoy_m(\d{2})_quantile", feature)
    if m:
        return f"{int(m.group(1))}月營收年增分位數"
    m = re.fullmatch(r"rev_mom_m(\d{2})_m(\d{1,2})_quantile", feature)
    if m:
        return f"{int(m.group(1))}月相對{int(m.group(2))}月營收月增分位數"
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train shared LightGBM model for models_eps/<year>/<month>"
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="01~12")
    return parser.parse_args()


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path, Path]:
    month_str = str(args.month).zfill(2)
    if month_str < "01" or month_str > "12":
        raise ValueError("--month 必須是 01~12")
    month_dir = (
        Path.cwd() / "train_eps" / "output" / str(args.year) / month_str
    ).resolve()
    models_dir = (Path.cwd() / "models_eps" / str(args.year) / month_str).resolve()

    dataset = month_dir / "dataset_train.csv"
    metrics_out = models_dir / "train_metrics.json"
    importance_out = models_dir / "feature_importance.json"

    return month_dir, dataset, models_dir, metrics_out, importance_out


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
    month_dir, dataset_path, models_dir, metrics_out, importance_out = resolve_paths(
        args
    )
    config, config_path = load_shared_config()
    common_cfg = config["common"]
    lgb_cfg = config["lightgbm-train"]

    seed = int(common_cfg["seed"])
    winsor_quantile = float(common_cfg["winsor_quantile"])
    n_jobs = int(common_cfg["n_jobs"])
    n_estimators = int(lgb_cfg["n_estimators"])
    learning_rate = float(lgb_cfg["learning_rate"])
    num_leaves = int(lgb_cfg["num_leaves"])
    subsample = float(lgb_cfg["subsample"])
    colsample_bytree = float(lgb_cfg["colsample_bytree"])
    reg_alpha = float(lgb_cfg["reg_alpha"])
    reg_lambda = float(lgb_cfg["reg_lambda"])

    df = (
        pd.read_csv(dataset_path)
        .replace([np.inf, -np.inf], np.nan)
        .dropna(subset=[TARGET, TARGET_DELTA])
    )

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

    winsor_cols = [c for c in use_features if c != "anchor_eps"] + [TARGET_DELTA]
    winsorize_inplace(df, winsor_cols, winsor_quantile)

    x_data = df[use_features]
    y_delta = df[TARGET_DELTA].astype(float).to_numpy()

    model = LGBMRegressor(
        objective="mae",
        n_estimators=n_estimators,
        learning_rate=learning_rate,
        num_leaves=num_leaves,
        subsample=subsample,
        colsample_bytree=colsample_bytree,
        reg_alpha=reg_alpha,
        reg_lambda=reg_lambda,
        random_state=seed,
        n_jobs=n_jobs,
    )
    model.fit(x_data, y_delta)

    pred_eps_from_delta = df["anchor_eps"].to_numpy(dtype=float) + model.predict(x_data)
    baseline_eps = df["anchor_eps"].to_numpy(dtype=float)
    y_true = df[TARGET].to_numpy(dtype=float)

    metrics = {
        "month_dir": str(month_dir),
        "config_path": str(config_path),
        "n_rows": int(len(df)),
        "main_metric": "mae",
        "winsor_quantile": winsor_quantile,
        "model_family": "lightgbm",
        "train_mae_lgb_pred_eps": float(
            mean_absolute_error(y_true, pred_eps_from_delta)
        ),
        "train_mae_baseline_anchor_eps": float(
            mean_absolute_error(y_true, baseline_eps)
        ),
        "feature_transform": "quantile",
        "features": use_features,
    }

    importance_df = pd.DataFrame(
        {"feature": use_features, "importance": model.feature_importances_}
    )
    importance_df["feature_cht"] = importance_df["feature"].map(feature_cht_name)
    missing_cht = sorted(
        importance_df.loc[importance_df["feature_cht"].isna(), "feature"].tolist()
    )
    if missing_cht:
        raise ValueError(f"Missing Chinese label for features: {missing_cht}")
    importance_df = importance_df.sort_values("importance", ascending=False)

    lgb_mae = metrics["train_mae_lgb_pred_eps"]
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    model_out = models_dir / f"{ts}_{lgb_mae:.3f}.pkl"

    models_dir.mkdir(parents=True, exist_ok=True)
    with open(model_out, "wb") as f:
        pickle.dump(model, f)
    metrics_out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    importance_df.to_json(importance_out, orient="records", force_ascii=False, indent=2)

    # sanity check: in-sample MAE 應低於 baseline，否則代表訓練有嚴重問題
    bl_mae = metrics["train_mae_baseline_anchor_eps"]
    if lgb_mae > bl_mae:
        log_path = BASE_DIR.parent / "error_train_eps.log"
        ts = datetime.now().isoformat(timespec="seconds")
        msg = (
            f"[{ts}] SANITY FAIL | {month_dir}\n"
            f"  train_mae_lgb_pred_eps ({lgb_mae:.4f}) > train_mae_baseline_anchor_eps ({bl_mae:.4f})\n"
            f"  模型 in-sample 表現劣於 baseline，請確認 feature/label 是否正確串接。\n"
        )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(msg)
        print(f"[WARNING] sanity check failed — 詳見 {log_path}")

    print(f"train completed: {month_dir.name}")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
