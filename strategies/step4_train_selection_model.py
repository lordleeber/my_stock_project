"""
使用歷史特徵-報酬對訓練選股模型（LightGBM Ranker，lambdarank）。

排名目標：
  每個月份內對股票指定 relevance label（0 = 最低報酬，n-1 = 最高報酬）。
  LightGBM 學習在同一個月內排序股票，使標籤最高的股票排在最前面。

輸入：  strategies/output/feature_return_analysis.csv
輸出：  models_selection/<YYYY-MM-DD>/selection_model.pkl
                                       feature_importance.csv
                                       latest.json
        其中 <YYYY-MM-DD> = train_through cohort 的 **playbook run date**（cutoff +1）

Walk-forward 設計（術語見 strategies/CLAUDE.md § Date Convention）：
  - train_through_playbook_date = 訓練資料 cohort 上界的 playbook run date（YYYY-MM-DD，
    = 該 cohort 的 cutoff_date + 1 calendar day；目錄名與 CLI `--date` 都用這個值）
  - train_through_cutoff_date   = 該 cohort 的 cutoff_date（公告日，PIT 截斷用）
  - 訓練資料：(year, month) <= train_through 的 cohort
  - 評估資料：(year, month) > train_through 的 cohort
  - 預設：不指定 `--date` → 用所有可用資料（生產模式，train_through="all"）

⚠ 不要把 `train_through_playbook_date` 跟 target cohort 的 `playbook_date` 搞混：
   train_through 的 = "這顆 model 看過資料看到哪天"
   target 的       = "step5 對哪一天的 candidates 評分"
   兩者差一個 cycle。

用法：
  # 使用所有資料訓練（生產）
  venv/bin/python3 strategies/step4_train_selection_model.py

  # Walk-forward 訓練：train_through playbook_date = 2024-06-11（cutoff 2024-06-10）
  venv/bin/python3 strategies/step4_train_selection_model.py --date 2024-06-11

  # Multi-seed ensemble：訓 K 顆（seeds = [seed..seed+K-1]），step5 平均其預測。
  # n_seeds=1（預設）維持單顆行為與舊 payload 格式 {"model", "feature_cols"}；
  # n_seeds>1 存 {"models":[...], "feature_cols", "seeds", "ensemble":True}。
  venv/bin/python3 strategies/step4_train_selection_model.py --date 2024-06-11 --n-seeds 10
  # --models-root 改輸出根目錄（平行/隔離訓練用，預設 models_selection/）
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import lightgbm as lgb
except ImportError:
    print("lightgbm not installed. Run: pip install lightgbm")
    sys.exit(1)

from strategies.feature_engineering import REVENUE_FEATURE_COLS, TECHNICAL_FEATURE_COLS
from strategies.shared_config import (
    cutoff_date_from_playbook,
    year_month_from_playbook,
)

FEATURE_COLS = (
    [
        "base_eps_growth_pct",
        "ml_eps_delta_pct",
        "eps_growth_total_pct",
        "pe_current",
        "ttm_eps",
        "volume_lots",
        "foreign_held_ratio",
        "trust_held_ratio",
        "large_holder_ratio",
        "large_holder_ratio_wow",
        "mid_holder_ratio",
        "mid_holder_ratio_wow",
        "small_holder_ratio",
        "small_holder_ratio_wow",
        "concentration_spread",
        "concentration_spread_wow",
        # 估值
        "roe_official",
        "pe_percentile_official",
        # 市場情緒
        "dealer_held_ratio",
        "margin_usage_ratio",
        "short_cover_pressure",
        "sbl_sell_repay_ratio",
        # 財報品質
        "anchor_debt_ratio",
        "pb_ratio",
        "current_ratio",
    ]
    + TECHNICAL_FEATURE_COLS
    + REVENUE_FEATURE_COLS
)  # 包含 close_vs_ma5/10/20/60/240、k、d、rsi、macd、bb_position、月營收動能等

LABEL_COL = "fwd_return_pct"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Train LightGBM Ranker for stock selection."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Walk-forward 訓練上界 cohort 的 playbook run date YYYY-MM-DD"
            "（cutoff 公告日 +1；5/8/11 月 = 16 號，其餘月份 = 11 號）。"
            "不指定則用所有可用資料訓練（生產模式，train_through='all'）。"
        ),
    )
    parser.add_argument("--n-estimators", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    # num_leaves=15 / min_child_samples=15 is the lower-capacity config validated
    # over 30 seeds (issue #2 downstream): after the valuation_daily fix, the old
    # 31/5 ranker amplified a 0.3% training-feature change into a robust monthly
    # Sharpe regression (~0.62 vs baseline 0.70). Lowering capacity restores the
    # Sharpe distribution to baseline level (mean 0.707, 90% of seeds within the
    # 0.05 threshold) at equal PnL. Do NOT revert to 31/5 without re-validating.
    parser.add_argument("--num-leaves", type=int, default=15)
    # n_bins=10 / reg_alpha=0.05 / reg_lambda=0.1 are the production config — aligned
    # with step4_batch so the bare `step4 --date PREV` call in schedules/playbook_run.sh
    # produces the SAME model as the backtested walk-forward batch. (Previously these
    # defaulted to 5 / 0 / 0, silently diverging from the validated config.)
    parser.add_argument(
        "--n-bins",
        type=int,
        default=10,
        help="Number of label bins per month (5=quintile, 10=decile; production 10)",
    )
    parser.add_argument(
        "--reg-alpha",
        type=float,
        default=0.05,
        help="L1 regularization (production 0.05)",
    )
    parser.add_argument(
        "--reg-lambda",
        type=float,
        default=0.1,
        help="L2 regularization (production 0.1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="random_state for LGBMRanker (vary to probe model variance)",
    )
    parser.add_argument(
        "--min-child-samples",
        type=int,
        default=15,
        help="LGBMRanker min_child_samples (raise to reduce pick variance; "
        "15 validated over 30 seeds, see --num-leaves note)",
    )
    # Production default: 10-seed ensemble (seeds [seed..seed+9] = 42..51). Validated
    # 2026-06 to collapse the single-seed Sharpe lottery (sd ~0.049) to a stable centre
    # ~0.716 with flat PnL. Set --n-seeds 1 to recover the legacy single-seed behaviour
    # (payload reverts to {'model': ...}). See project_ensemble_validation_2026_06.
    parser.add_argument(
        "--n-seeds",
        type=int,
        default=10,
        help="Train an ensemble of N models with seeds "
        "[seed, seed+1, ..., seed+N-1]; step5 averages their predictions to "
        "neutralise single-seed variance. default 10 (production); 1 = single-seed "
        "(payload stays {'model': ...}).",
    )
    parser.add_argument(
        "--models-root",
        type=Path,
        default=None,
        help="Root dir for model output (default models_selection/). Point at an "
        "isolated dir for parallel validation runs so groups don't overwrite "
        "each other.",
    )
    return parser.parse_args()


def build_rank_labels(df: pd.DataFrame, n_bins: int = 5) -> pd.Series:
    """
    對每個 (year, month) 群組，依報酬指定 relevance label 0～(n_bins-1)。
    最高報酬 bucket = label n_bins-1，最低 = label 0。
    LightGBM lambdarank 最大化 NDCG，因此 label 越高 = 應排越前面。
    """
    labels = list(range(n_bins))

    def _bin(g: pd.Series) -> pd.Series:
        # 不再 silent fallback 到 binary median split — 訓練目標降階會讓 lambdarank
        # NDCG signal 在某些月份悄悄塌掉。qcut 失敗代表上游資料品質問題（該月
        # fwd_return 過於集中、unique 值不足以切 n_bins 個 quantile），請查
        # feature_return_analysis.csv 那個月份的分布是否異常。
        try:
            return pd.qcut(g, n_bins, labels=labels, duplicates="drop").astype(int)
        except Exception as exc:
            ym = g.name if isinstance(g.name, tuple) else (g.name, "?")
            raise RuntimeError(
                f"qcut failed for cohort year={ym[0]} month={ym[1]} "
                f"(n_rows={len(g)}, n_unique={g.nunique()}, n_bins={n_bins}): {exc}. "
                f"檢查 feature_return_analysis.csv 該月份 fwd_return_pct 分布；"
                f"若該月 cohort 樣本太少或報酬過於集中，請考慮排除或調整 --n-bins。"
            ) from exc

    return df.groupby(["year", "month"], group_keys=False)[LABEL_COL].apply(_bin)


def build_groups(df: pd.DataFrame) -> list[int]:
    """回傳每個月的 group 大小列表（每月股票數），依列順序排列。"""
    return df.groupby(["year", "month"], sort=False).size().tolist()


def spearman_ic(df: pd.DataFrame, pred: np.ndarray) -> float:
    """計算模型預測分數與實際報酬的整體 Spearman IC。"""
    return pd.Series(pred).corr(pd.Series(df[LABEL_COL].values), method="spearman")


def monthly_ic(df: pd.DataFrame, pred: np.ndarray) -> pd.DataFrame:
    """計算每個月份的 Spearman IC。"""
    tmp = df[["year", "month", LABEL_COL]].copy()
    tmp["pred"] = pred
    ic = (
        tmp.groupby(["year", "month"])
        .apply(
            lambda g: g["pred"].corr(g[LABEL_COL], method="spearman"),
            include_groups=False,
        )
        .reset_index(name="ic")
    )
    return ic


def main() -> None:
    args = parse_args()

    data_path = (
        ROOT_DIR / "strategies" / "output" / "feature_return_analysis.csv"
    ).resolve()
    if not data_path.exists():
        print(f"Training data not found: {data_path}")
        print("Run: venv/bin/python3 strategies/analyze_feature_returns.py")
        sys.exit(1)

    df = pd.read_csv(data_path)
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df["month"] = df["month"].astype(str).str.zfill(2)
    df["ym"] = df["year"].astype(int) * 100 + df["month"].astype(int)

    # 必須排序，使每個月份的資料列連續（LGBMRanker group 參數要求）。
    df = df.sort_values(["year", "month"]).reset_index(drop=True)

    # Walk-forward 資料切分。
    if args.date is not None:
        tt_year, tt_month = year_month_from_playbook(args.date)
        train_through_ym = tt_year * 100 + int(tt_month)
        train_df = df[df["ym"] <= train_through_ym].copy()
        eval_df = df[df["ym"] > train_through_ym].copy()
        train_through_label = f"{tt_year:04d}/{tt_month}"
        train_through_playbook_date = args.date
        train_through_cutoff_date = cutoff_date_from_playbook(args.date)
    else:
        train_df = df.copy()
        eval_df = pd.DataFrame()
        train_through_label = "all"
        train_through_playbook_date = None
        train_through_cutoff_date = None

    print(
        f"Training data: {len(train_df)} rows  ({train_df['ym'].nunique()} months)  "
        f"train_through={train_through_label}"
        + (
            f" (playbook {train_through_playbook_date}, cutoff {train_through_cutoff_date})"
            if train_through_playbook_date
            else ""
        )
    )
    if not eval_df.empty:
        print(f"Eval data:     {len(eval_df)} rows  ({eval_df['ym'].nunique()} months)")

    missing = [c for c in FEATURE_COLS if c not in train_df.columns]
    if missing:
        raise RuntimeError(
            f"Training data missing required features: {missing}. "
            "feature_return_analysis.csv schema 與 step4 FEATURE_COLS 不同步 — "
            "可能 step3 漏帶欄位或 step1/2 沒產出該特徵。請修正 schema 後重跑，"
            "不要 silent 跳過特徵繼續訓練（會造成模型行為與 step5 不一致）。"
        )
    feat_cols = list(FEATURE_COLS)

    # 保留 NaN 讓 LightGBM 原生 NaN handling 學最佳分裂方向；不再 fillna(0)。
    X_train = train_df[feat_cols].apply(pd.to_numeric, errors="coerce")
    y_train = build_rank_labels(train_df, n_bins=args.n_bins)
    train_groups = build_groups(train_df)
    X_eval = (
        eval_df[feat_cols].apply(pd.to_numeric, errors="coerce")
        if not eval_df.empty
        else None
    )

    # Multi-seed ensemble：對 seeds = [seed, seed+1, ..., seed+n_seeds-1] 各訓一顆，
    # step5 平均其預測以壓掉單 seed 變異（~1/sqrt(K)）。n_seeds=1 = 現行單顆行為。
    seeds = list(range(args.seed, args.seed + args.n_seeds))
    is_ensemble = len(seeds) > 1
    if is_ensemble:
        print(f"Training {len(seeds)}-seed ensemble: seeds={seeds}")

    models: list[lgb.LGBMRanker] = []
    train_preds: list[np.ndarray] = []
    eval_preds: list[np.ndarray] = []
    for s in seeds:
        m = lgb.LGBMRanker(
            objective="lambdarank",
            n_estimators=args.n_estimators,
            learning_rate=args.learning_rate,
            num_leaves=args.num_leaves,
            subsample=0.8,
            subsample_freq=1,  # subsample 需要 freq>0 才生效，預設 0 等於 silently disabled
            colsample_bytree=0.8,
            min_child_samples=args.min_child_samples,
            reg_alpha=args.reg_alpha,
            reg_lambda=args.reg_lambda,
            random_state=s,
            verbose=-1,
        )
        m.fit(X_train, y_train, group=train_groups)
        models.append(m)
        train_preds.append(m.predict(X_train))
        if X_eval is not None:
            eval_preds.append(m.predict(X_eval))

    # IC 用 ensemble 平均預測（單顆時即該顆預測）— 反映 ensemble 實際排序行為。
    train_pred = np.mean(train_preds, axis=0)
    train_ic = spearman_ic(train_df, train_pred)
    print(f"Train Spearman IC: {train_ic:.4f}")

    eval_ic = None
    if X_eval is not None:
        eval_pred = np.mean(eval_preds, axis=0)
        eval_ic = spearman_ic(eval_df, eval_pred)
        print(f"Eval  Spearman IC: {eval_ic:.4f}")

        mic = monthly_ic(eval_df, eval_pred)
        print(
            f"\nMonthly IC (eval period)  mean={mic['ic'].mean():.4f}  std={mic['ic'].std():.4f}:"
        )
        print(mic.to_string(index=False))

    # 特徵重要性（K 顆平均；單顆時即該顆）。
    importance = pd.DataFrame(
        {
            "feature": feat_cols,
            "importance_gain": np.mean(
                [m.booster_.feature_importance(importance_type="gain") for m in models],
                axis=0,
            ),
            "importance_split": np.mean(
                [
                    m.booster_.feature_importance(importance_type="split")
                    for m in models
                ],
                axis=0,
            ),
        }
    ).sort_values("importance_gain", ascending=False)
    print("\nFeature importance (gain, top 20):")
    print(importance.head(20).to_string(index=False))

    # 儲存模型。
    models_root = (
        args.models_root.resolve()
        if args.models_root is not None
        else (ROOT_DIR / "models_selection").resolve()
    )
    out_dir = (
        models_root / (args.date if args.date is not None else "latest")
    ).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "selection_model.pkl"
    with open(model_path, "wb") as f:
        if is_ensemble:
            pickle.dump(
                {
                    "models": models,
                    "feature_cols": feat_cols,
                    "seeds": seeds,
                    "ensemble": True,
                },
                f,
            )
        else:
            # 單顆：維持現行 payload 格式，向後相容（產出與舊版等價）。
            pickle.dump({"model": models[0], "feature_cols": feat_cols}, f)

    importance.to_csv(out_dir / "feature_importance.csv", index=False)

    meta = {
        "model_path": str(model_path),
        "objective": "lambdarank",
        "feature_cols": feat_cols,
        "train_through": train_through_label,
        "train_through_playbook_date": train_through_playbook_date,
        "train_through_cutoff_date": train_through_cutoff_date,
        "train_rows": int(len(train_df)),
        "train_months": int(train_df["ym"].nunique()),
        "train_spearman_ic": round(float(train_ic), 4),
        "eval_spearman_ic": round(float(eval_ic), 4) if eval_ic is not None else None,
        "params": {
            "n_estimators": args.n_estimators,
            "learning_rate": args.learning_rate,
            "num_leaves": args.num_leaves,
            "min_child_samples": args.min_child_samples,
            "reg_alpha": args.reg_alpha,
            "reg_lambda": args.reg_lambda,
            "seed": args.seed,
            "n_seeds": args.n_seeds,
            "seeds": seeds,
            "ensemble": is_ensemble,
        },
    }
    (out_dir / "latest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nModel saved: {model_path}")


if __name__ == "__main__":
    main()
