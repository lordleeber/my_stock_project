"""
使用 walk-forward 選股模型對 target cohort 的候選股評分。

輸入：  strategies/output/<YYYY-MM-DD>/dataset_strategy.csv     （target cohort，<YYYY-MM-DD> = target playbook date）
模型：  walk-forward 挑「train_through playbook_date 嚴格早於 target」的最新模型，
        來自 models_selection/<YYYY-MM-DD>/
輸出：  models_selection/<YYYY-MM-DD>/candidates_scored.csv     （target cohort）

術語見 strategies/CLAUDE.md § Date Convention：
  target playbook_date         = CLI `--date`（YYYY-MM-DD，cutoff +1）
  target cutoff_date           = target 的 PIT 截斷日（=dataset_strategy.csv.quote_date 假日修正前）
  train_through_playbook_date  = 模型訓練資料 cohort 上界的 playbook run date

用法：
  venv/bin/python3 strategies/step5_score_and_publish.py --date 2024-07-11
  venv/bin/python3 strategies/step5_score_and_publish.py --date 2025-10-11 --model-dir models_selection/latest
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.shared_config import (  # noqa: E402
    cutoff_date_from_playbook,
    latest_playbook_date,
    parse_playbook_date,
)


def resolve_model_for_target(
    models_root: Path, target_playbook_date: str
) -> Path | None:
    """回傳 train_through_playbook_date 嚴格早於 target 的最新模型目錄。

    `models_selection/<YYYY-MM-DD>/` 下 `<YYYY-MM-DD>` 是 canonical playbook date。
    `latest/` 與其他非 canonical 命名會被略過。
    """
    if not models_root.exists():
        return None
    best: tuple[str, Path] | None = None
    for d in sorted(models_root.iterdir()):
        if not d.is_dir() or d.name == "latest":
            continue
        try:
            parse_playbook_date(d.name)
        except ValueError:
            continue
        if d.name < target_playbook_date and (d / "selection_model.pkl").exists():
            if best is None or d.name > best[0]:
                best = (d.name, d)
    return best[1] if best else None


def ensemble_score(models: list, X: pd.DataFrame, agg: str) -> np.ndarray:
    """把 K 顆模型的預測合成單一 ml_score（越大越好，給 run_rolling 降冪排序用）。

    - 單顆（len==1）+ agg='score'：等價於 model.predict(X)，向後相容。
    - agg='score'：平均各顆原始 predict 分數。
    - agg='rank' ：每顆先在候選集內算 rank（1=最佳），平均後取負（-mean_rank
                   仍越大越好）。對各顆 score scale 差異較 robust。
    """
    preds = [pd.Series(m.predict(X), index=X.index) for m in models]
    if agg == "score":
        return np.mean([p.to_numpy() for p in preds], axis=0)
    if agg == "rank":
        ranks = [p.rank(ascending=False, method="average") for p in preds]
        mean_rank = np.mean([r.to_numpy() for r in ranks], axis=0)
        return -mean_rank
    raise ValueError(f"unknown ensemble agg: {agg!r} (expected 'score' or 'rank')")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score candidates using walk-forward selection model."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target playbook run date YYYY-MM-DD（省略則用 latest_playbook_date()）",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="Override model dir (e.g. models_selection/latest for production pick)",
    )
    parser.add_argument(
        "--models-root",
        type=Path,
        default=None,
        help="Root dir for model lookup + candidates_scored.csv output "
        "(default models_selection/). Use an isolated dir for parallel "
        "validation runs.",
    )
    parser.add_argument(
        "--ensemble-agg",
        choices=["score", "rank"],
        default="score",
        help="Combine an ensemble payload's K models: 'score' = mean of raw "
        "predict scores; 'rank' = mean of per-model ranks. No-op for "
        "single-model payloads.",
    )
    return parser.parse_args()


def score_and_publish(
    target_playbook_date: str,
    model_dir: Path | None = None,
    models_root: Path | None = None,
    agg: str = "score",
) -> Path:
    """對 target playbook date 的候選股評分，並將 candidates_scored.csv 寫入 <models_root>/<DATE>/。"""
    parse_playbook_date(target_playbook_date)

    ds_path = (
        ROOT_DIR
        / "strategies"
        / "output"
        / target_playbook_date
        / "dataset_strategy.csv"
    )
    if not ds_path.exists():
        raise FileNotFoundError(
            f"dataset_strategy.csv not found: {ds_path}\n"
            f"Run: venv/bin/python3 strategies/step2_finalize_strategy.py --date {target_playbook_date}"
        )

    models_root = models_root or (ROOT_DIR / "models_selection")
    if model_dir is None:
        model_dir = resolve_model_for_target(models_root, target_playbook_date)
        if model_dir is None:
            raise FileNotFoundError(
                f"No selection model found for target {target_playbook_date} "
                f"(need train_through_playbook_date < {target_playbook_date} in {models_root}). "
                f"Run: venv/bin/python3 strategies/step4_batch_train_selection_model.py"
            )

    model_path = model_dir / "selection_model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"selection_model.pkl not found: {model_path}")

    with open(model_path, "rb") as f:
        payload = pickle.load(f)
    feature_cols = payload["feature_cols"]
    if "models" in payload:
        # Ensemble payload（step4 --n-seeds > 1）。
        models = payload["models"]
        ens_seeds = payload.get("seeds")
    else:
        # 單顆 payload（含磁碟上既有舊格式）。
        models = [payload["model"]]
        ens_seeds = payload.get("seeds")

    df = pd.read_csv(ds_path)
    df["symbol"] = df["symbol"].astype(str).str.strip()

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"dataset_strategy.csv missing model features: {missing}. "
            f"Model {model_path} 訓練看過這些特徵，但 scoring 端 dataset_strategy.csv "
            "沒有對應欄位 — 代表 step1/2 ↔ step4 schema 不同步。請補齊欄位後重跑，"
            "不要 silent 補 NaN 繼續評分（model 從沒看過該欄為 NaN 的訓練樣本，預測不可信）。"
        )

    X = df[feature_cols].apply(pd.to_numeric, errors="coerce")
    df["ml_score"] = ensemble_score(models, X, agg)
    df["ml_rank"] = df["ml_score"].rank(ascending=False, method="first").astype(int)

    # Ensemble traceability：單顆 → k=1 / agg=single / seeds 空（舊 payload 無 seed）。
    is_ensemble = len(models) > 1
    df["scored_by_ensemble_k"] = len(models)
    df["scored_by_ensemble_seeds"] = (
        ",".join(str(s) for s in ens_seeds) if ens_seeds else ""
    )
    df["scored_by_ensemble_agg"] = agg if is_ensemble else "single"

    # 標註此次評分使用的 model 的 train_through（walk-forward 來源），
    # 避免日後看 candidates_scored.csv 誤以為是當月訓練的模型打的分。
    # train_through_playbook_date = YYYY-MM-DD，目錄名直接是值。
    # train_through_cutoff_date   = 該 cohort 的公告日（playbook - 1 calendar day）。
    if model_dir.name == "latest":
        # latest 目錄無 canonical playbook date — 來源歧義；不寫日期欄。
        df["scored_by_train_through_playbook_date"] = "latest"
        df["scored_by_train_through_cutoff_date"] = ""
    else:
        df["scored_by_train_through_playbook_date"] = model_dir.name
        df["scored_by_train_through_cutoff_date"] = cutoff_date_from_playbook(
            model_dir.name
        )

    out = df.sort_values("ml_rank").reset_index(drop=True)

    out_dir = models_root / target_playbook_date
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "candidates_scored.csv"
    out.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"scored {len(out)} candidates → {out_path}")
    print(f"model used: {model_dir}")
    show_cols = [
        c
        for c in [
            "symbol",
            "name",
            "ml_rank",
            "ml_score",
            "ml_eps_delta_pct",
            "base_eps_growth_pct",
            "pe_current",
            "ttm_eps",
            "close_vs_ma240",
        ]
        if c in out.columns
    ]
    print("\nTop 15 by ml_score:")
    print(out[show_cols].head(15).to_string(index=False))

    return out_path


def main() -> None:
    args = parse_args()
    target = args.date or latest_playbook_date()
    if args.date is None:
        print(f"[auto] --date 未指定，使用最新 canonical playbook date: {target}")
    score_and_publish(
        target,
        model_dir=args.model_dir,
        models_root=args.models_root,
        agg=args.ensemble_agg,
    )


if __name__ == "__main__":
    main()
