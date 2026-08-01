#!/usr/bin/env python3
"""產出某個 selection model 的特徵分析報告(SHAP 方向性 + 跨月 importance 漂移)。

用法(從 repo root 執行):
    venv/bin/python3 tools/feature_analysis_report.py --model-date 2026-05-16
    venv/bin/python3 tools/feature_analysis_report.py --model-date 2026-05-16 --scored-date 2026-06-11

--model-date   : 帶 selection_model.pkl 的 train_through 目錄(必填)
--scored-date  : 要算 SHAP 的 candidates_scored.csv 月份。省略時自動找
                 scored_by_train_through_playbook_date == model-date 的最新 picks。
--drift-n      : 跨月漂移取最近 N 個模型(預設 8)

輸出到 models_selection/<model-date>/:
    shap_directionality.csv  importance_drift.csv  feature_analysis.md

SHAP 用 LightGBM 原生 TreeSHAP(predict(pred_contrib=True)),不需安裝 shap 套件。
"""

import argparse
import glob
import os
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = ROOT / "models_selection"


def load_ensemble(pkl_path):
    with open(pkl_path, "rb") as f:
        obj = pickle.load(f)
    if obj.get("ensemble"):
        models = obj["models"]
    elif "model" in obj:
        models = [obj["model"]]
    else:
        models = obj.get("models", [])
    return models, obj["feature_cols"]


def gain_importance(models, feats):
    g = np.zeros(len(feats))
    for mdl in models:
        bst = mdl.booster_ if hasattr(mdl, "booster_") else mdl
        g += np.array(bst.feature_importance(importance_type="gain"))
    g /= len(models)
    return g / g.sum() * 100


def auto_scored_date(model_date):
    """找 scored_by_train_through_playbook_date == model_date 的最新 picks 目錄。"""
    hits = []
    for p in sorted(glob.glob(str(MODELS_ROOT / "*" / "candidates_scored.csv"))):
        try:
            head = pd.read_csv(p, nrows=1)
        except Exception:
            continue
        col = "scored_by_train_through_playbook_date"
        if col in head.columns and str(head[col].iloc[0]) == model_date:
            hits.append(os.path.basename(os.path.dirname(p)))
    if not hits:
        raise SystemExit(
            f"找不到由 {model_date} 模型打分的 candidates_scored.csv;請用 --scored-date 指定。"
        )
    return sorted(hits)[-1]


def direction_label(c):
    if np.isnan(c):
        return "flat"
    if c > 0.5:
        return "strong_up"
    if c > 0.2:
        return "up"
    if c < -0.5:
        return "strong_down"
    if c < -0.2:
        return "down"
    return "non_monotonic"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--model-date",
        required=True,
        help="train_through 目錄(含 selection_model.pkl),YYYY-MM-DD",
    )
    ap.add_argument(
        "--scored-date",
        default=None,
        help="算 SHAP 的 candidates_scored.csv 月份;省略則自動偵測",
    )
    ap.add_argument(
        "--drift-n", type=int, default=8, help="跨月漂移取最近 N 個模型(預設 8)"
    )
    args = ap.parse_args()

    model_date = args.model_date
    outdir = MODELS_ROOT / model_date
    pkl = outdir / "selection_model.pkl"
    if not pkl.exists():
        raise SystemExit(f"找不到模型:{pkl}")

    scored_date = args.scored_date or auto_scored_date(model_date)
    scored_csv = MODELS_ROOT / scored_date / "candidates_scored.csv"
    if not scored_csv.exists():
        raise SystemExit(f"找不到 candidates:{scored_csv}")

    models, feats = load_ensemble(pkl)
    print(
        f"model={model_date} ({len(models)} members, {len(feats)} feats) | scored_on={scored_date}"
    )

    # ---- SHAP directionality (native TreeSHAP, averaged over ensemble) ----
    df = pd.read_csv(scored_csv)
    X = df[feats].astype(float)
    shap_sum = np.zeros((len(X), len(feats)))
    for mdl in models:
        bst = mdl.booster_ if hasattr(mdl, "booster_") else mdl
        shap_sum += bst.predict(X, pred_contrib=True)[:, :-1]
    shap = shap_sum / len(models)

    mean_abs = np.abs(shap).mean(axis=0)
    dir_corr = np.array(
        [
            spearmanr(X.iloc[:, j], shap[:, j], nan_policy="omit")[0]
            for j in range(len(feats))
        ]
    )
    gain_now = gain_importance(models, feats)

    shap_df = (
        pd.DataFrame(
            {
                "feature": feats,
                "gain_pct": gain_now.round(3),
                "shap_pct": (mean_abs / mean_abs.sum() * 100).round(3),
                "direction_spearman": dir_corr.round(3),
            }
        )
        .sort_values("shap_pct", ascending=False)
        .reset_index(drop=True)
    )
    shap_df["direction"] = shap_df["direction_spearman"].map(direction_label)
    shap_df.to_csv(outdir / "shap_directionality.csv", index=False)

    # ---- cross-month importance drift ----
    dirs = sorted(glob.glob(str(MODELS_ROOT / "*" / "selection_model.pkl")))[
        -args.drift_n :
    ]
    table = {}
    for p in dirs:
        d = os.path.basename(os.path.dirname(p))
        m, f = load_ensemble(p)
        table[d] = dict(zip(f, gain_importance(m, f)))
    drift = pd.DataFrame(table).round(3)
    last = drift.columns[-1]
    drift = drift.sort_values(last, ascending=False)
    drift.to_csv(outdir / "importance_drift.csv")

    # ---- markdown report ----
    lines = [
        f"# Selection Model 特徵分析 — train_through {model_date}",
        "",
        f"- 模型:`models_selection/{model_date}/selection_model.pkl`"
        f"(LGBMRanker ensemble, {len(models)} members, {len(feats)} 特徵)",
        f"- 打分對象:`models_selection/{scored_date}/candidates_scored.csv`(walk-forward 該月生產 picks)",
        "- SHAP:LightGBM 原生 TreeSHAP(`predict(pred_contrib=True)`),ensemble 成員平均",
        "- 方向(direction_spearman):feature 值 vs 其 SHAP 的 Spearman。+ 單調拉高分數,− 拉低,~0 非單調",
        "",
        "## SHAP 全域重要性 + 方向(Top 20)",
        "",
        "| feature | gain% | shap% | dir | label |",
        "|---|--:|--:|--:|---|",
    ]
    for _, r in shap_df.head(20).iterrows():
        lines.append(
            f"| {r.feature} | {r.gain_pct:.2f}% | {r.shap_pct:.2f}% | "
            f"{r.direction_spearman:+.2f} | {r.direction} |"
        )
    lines += [
        "",
        "## ⚠️ 方法論注記",
        "",
        "- **不可用 picks-vs-pool 中位數推方向**:最終排名是所有特徵 SHAP 的加總,"
        "個股可靠其他特徵被拉上來,單一特徵的 picks 中位可能與 pool 中位持平卻仍強單調。",
        "- SHAP 方向在當期候選池上估計,分布外可能不同;Spearman 僅衡量單調性,交互項不完整顯示。",
        "",
        f"## 跨月 importance 漂移(最近 {len(drift.columns)} 個模型,gain%)",
        "",
        "| feature | " + " | ".join(drift.columns) + " |",
        "|---" + "|--:" * len(drift.columns) + "|",
    ]
    for feat, row in drift.head(12).iterrows():
        lines.append(
            f"| {feat} | " + " | ".join(f"{row[c]:.2f}" for c in drift.columns) + " |"
        )
    lines.append("")

    (outdir / "feature_analysis.md").write_text("\n".join(lines))

    print("wrote:")
    for fn in [
        "shap_directionality.csv",
        "importance_drift.csv",
        "feature_analysis.md",
    ]:
        print(f"  {outdir / fn}")


if __name__ == "__main__":
    main()
