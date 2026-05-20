"""
使用 walk-forward 選股模型對 target cohort 的候選股評分。

輸入：  strategies/output/<YYYY-MM-DD>/dataset_strategy.csv     （target cohort，<YYYY-MM-DD> = target playbook date）
模型：  walk-forward 挑「train_through playbook_date 嚴格早於 target」的最新模型，
        來自 models_selection/<YYYY-MM-DD>/
輸出：  models_selection/<YYYY-MM-DD>/candidates_scored.csv     （target cohort）

術語見 strategies/CLAUDE.md § Date Convention：
  target playbook_date         = CLI `--date`（YYYY-MM-DD，cutoff +1）
  target cutoff_date           = target 的 PIT 截斷日（=dataset_strategy.csv.quote_date 假日修正前）
  train_through_playbook_date  = 模型訓練資料 cohort 上界的 playbook release date

用法：
  venv/bin/python3 strategies/step5_score_and_publish.py --date 2024-07-11
  venv/bin/python3 strategies/step5_score_and_publish.py --date 2025-10-11 --model-dir models_selection/latest
"""

from __future__ import annotations

import argparse
import pickle
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.shared_config import (  # noqa: E402
    cutoff_date_from_playbook,
    latest_playbook_date,
    parse_playbook_date,
)


def resolve_model_for_target(models_root: Path, target_playbook_date: str) -> Path | None:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score candidates using walk-forward selection model."
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target playbook release date YYYY-MM-DD（省略則用 latest_playbook_date()）",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="Override model dir (e.g. models_selection/latest for production pick)",
    )
    return parser.parse_args()


def score_and_publish(
    target_playbook_date: str, model_dir: Path | None = None
) -> Path:
    """對 target playbook date 的候選股評分，並將 candidates_scored.csv 寫入 models_selection/<DATE>/。"""
    parse_playbook_date(target_playbook_date)

    ds_path = (
        ROOT_DIR / "strategies" / "output" / target_playbook_date / "dataset_strategy.csv"
    )
    if not ds_path.exists():
        raise FileNotFoundError(
            f"dataset_strategy.csv not found: {ds_path}\n"
            f"Run: venv/bin/python3 strategies/step2_finalize_strategy.py --date {target_playbook_date}"
        )

    models_root = ROOT_DIR / "models_selection"
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
    model = payload["model"]
    feature_cols = payload["feature_cols"]

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
    df["ml_score"] = model.predict(X)
    df["ml_rank"] = df["ml_score"].rank(ascending=False, method="first").astype(int)

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

    out_dir = ROOT_DIR / "models_selection" / target_playbook_date
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
            "pred_upside_pct",
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
    score_and_publish(target, model_dir=args.model_dir)


if __name__ == "__main__":
    main()
