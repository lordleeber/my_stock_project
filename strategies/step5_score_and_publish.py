"""
使用 walk-forward 選股模型對 target cohort 的候選股評分。

輸入：  strategies/output/<year>/<month>/dataset_strategy.csv     （target cohort）
模型：  walk-forward 挑「train_through 嚴格早於 target」的最新模型，
        來自 models_selection/<train_through_year>/<train_through_month>/
輸出：  models_selection/<year>/<month>/candidates_scored.csv     （target cohort）

術語見 strategies/CLAUDE.md § Date Convention：
  cutoff_date         = target cohort 的 PIT 截斷日（dataset_strategy.csv.quote_date）
  train_through_date  = 模型訓練資料 cohort 上界的 cutoff_date

用法：
  venv/bin/python3 strategies/step5_score_and_publish.py --year 2024 --month 7
  venv/bin/python3 strategies/step5_score_and_publish.py --year 2025 --month 10 --model-dir models_selection/latest
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

from strategies.step1_prepare_data import model_release_date  # noqa: E402


def resolve_model_for_month(models_root: Path, year: int, month: int) -> Path | None:
    """回傳 train_through 嚴格早於 target (year, month) 的最新模型目錄。"""
    target_ym = year * 100 + month
    best: tuple[int, Path] | None = None

    for y_dir in sorted(models_root.iterdir()):
        if not y_dir.is_dir() or y_dir.name == "latest":
            continue
        try:
            y = int(y_dir.name)
        except ValueError:
            continue
        for m_dir in sorted(y_dir.iterdir()):
            if not m_dir.is_dir():
                continue
            try:
                m = int(m_dir.name)
            except ValueError:
                continue
            train_through_ym = y * 100 + m
            if (
                train_through_ym < target_ym
                and (m_dir / "selection_model.pkl").exists()
            ):
                if best is None or train_through_ym > best[0]:
                    best = (train_through_ym, m_dir)

    return best[1] if best else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score candidates using walk-forward selection model."
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=None,
        help="Override model dir (e.g. models_selection/latest for production pick)",
    )
    return parser.parse_args()


def score_and_publish(year: int, month: int, model_dir: Path | None = None) -> Path:
    """對 year/month 的候選股評分，並將 candidates_scored.csv 寫入 models_selection/<year>/<month>/。"""
    month_s = str(month).zfill(2)

    ds_path = (
        ROOT_DIR
        / "strategies"
        / "output"
        / f"{year:04d}"
        / month_s
        / "dataset_strategy.csv"
    )
    if not ds_path.exists():
        raise FileNotFoundError(
            f"dataset_strategy.csv not found: {ds_path}\n"
            f"Run: venv/bin/python3 strategies/finalize_strategy.py --year {year} --month {month}"
        )

    models_root = ROOT_DIR / "models_selection"
    if model_dir is None:
        model_dir = resolve_model_for_month(models_root, year, month)
        if model_dir is None:
            raise FileNotFoundError(
                f"No selection model found for target {year}/{month_s} "
                f"(need train_through < {year}/{month_s} in {models_root}). "
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
        print(
            f"[WARN] features missing in dataset_strategy.csv (will be filled with 0): {missing}"
        )

    # 缺欄位填 NaN（不是 0），與 step4 訓練端對齊：LightGBM 原生 NaN handling。
    for c in feature_cols:
        if c not in df.columns:
            df[c] = np.nan

    X = df[feature_cols].apply(pd.to_numeric, errors="coerce")
    df["ml_score"] = model.predict(X)
    df["ml_rank"] = df["ml_score"].rank(ascending=False, method="first").astype(int)
    # 標註此次評分使用的 model 的 train_through（walk-forward 來源），
    # 避免日後看 candidates_scored.csv 誤以為是當月訓練的模型打的分。
    # train_through       = "YYYY/MM"   訓練資料 cohort 上界（cohort 級標籤）
    # train_through_date  = "YYYY-MM-DD" 該 cohort 的 cutoff_date（具體日期，避免歧義）
    tt_label = f"{model_dir.parent.name}/{model_dir.name}"
    df["scored_by_train_through"] = tt_label
    try:
        df["scored_by_train_through_date"] = model_release_date(
            int(model_dir.parent.name), model_dir.name
        )
    except Exception:
        df["scored_by_train_through_date"] = None

    out = df.sort_values("ml_rank").reset_index(drop=True)

    out_dir = ROOT_DIR / "models_selection" / f"{year:04d}" / month_s
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
    year = int(args.year)
    month = str(args.month).zfill(2)
    score_and_publish(year, int(month), model_dir=args.model_dir)


if __name__ == "__main__":
    main()
