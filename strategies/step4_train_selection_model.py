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
        "large_holder_two_week_up",
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
    parser.add_argument("--num-leaves", type=int, default=31)
    parser.add_argument(
        "--n-bins",
        type=int,
        default=5,
        help="Number of label bins per month (default 5=quintile, 10=decile)",
    )
    parser.add_argument(
        "--reg-alpha", type=float, default=0.0, help="L1 regularization"
    )
    parser.add_argument(
        "--reg-lambda", type=float, default=0.0, help="L2 regularization"
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

    model = lgb.LGBMRanker(
        objective="lambdarank",
        n_estimators=args.n_estimators,
        learning_rate=args.learning_rate,
        num_leaves=args.num_leaves,
        subsample=0.8,
        subsample_freq=1,  # subsample 需要 freq>0 才生效，預設 0 等於 silently disabled
        colsample_bytree=0.8,
        min_child_samples=5,
        reg_alpha=args.reg_alpha,
        reg_lambda=args.reg_lambda,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_train, y_train, group=train_groups)

    train_pred = model.predict(X_train)
    train_ic = spearman_ic(train_df, train_pred)
    print(f"Train Spearman IC: {train_ic:.4f}")

    eval_ic = None
    if not eval_df.empty:
        X_eval = eval_df[feat_cols].apply(pd.to_numeric, errors="coerce")
        eval_pred = model.predict(X_eval)
        eval_ic = spearman_ic(eval_df, eval_pred)
        print(f"Eval  Spearman IC: {eval_ic:.4f}")

        mic = monthly_ic(eval_df, eval_pred)
        print(
            f"\nMonthly IC (eval period)  mean={mic['ic'].mean():.4f}  std={mic['ic'].std():.4f}:"
        )
        print(mic.to_string(index=False))

    # 特徵重要性。
    importance = pd.DataFrame(
        {
            "feature": feat_cols,
            "importance_gain": model.booster_.feature_importance(
                importance_type="gain"
            ),
            "importance_split": model.booster_.feature_importance(
                importance_type="split"
            ),
        }
    ).sort_values("importance_gain", ascending=False)
    print("\nFeature importance (gain, top 20):")
    print(importance.head(20).to_string(index=False))

    # 儲存模型。
    if args.date is not None:
        out_dir = (ROOT_DIR / "models_selection" / args.date).resolve()
    else:
        out_dir = (ROOT_DIR / "models_selection" / "latest").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    model_path = out_dir / "selection_model.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_cols": feat_cols}, f)

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
        },
    }
    (out_dir / "latest.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nModel saved: {model_path}")


if __name__ == "__main__":
    main()
