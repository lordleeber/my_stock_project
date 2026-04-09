"""
使用 walk-forward 選股模型對當月候選股評分。

輸入：  strategies/output/<year>/<month>/dataset_strategy.csv
模型：  walk-forward（最新 cutoff < year/month），來自 models_selection/
輸出：  models_selection/<year>/<month>/candidates_scored.csv

用法：
  venv/bin/python3 strategies/score_and_publish.py --year 2024 --month 7
  venv/bin/python3 strategies/score_and_publish.py --year 2025 --month 10 --model-dir models_selection/latest
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


def resolve_model_for_month(models_root: Path, year: int, month: int) -> Path | None:
    """回傳 cutoff 嚴格早於 (year, month) 的最新模型目錄。"""
    ym = year * 100 + month
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
            cutoff_ym = y * 100 + m
            if cutoff_ym < ym and (m_dir / "selection_model.pkl").exists():
                if best is None or cutoff_ym > best[0]:
                    best = (cutoff_ym, m_dir)

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
                f"No selection model found for {year}/{month_s} "
                f"(need cutoff < {year}/{month_s} in {models_root}). "
                f"Run: venv/bin/python3 strategies/batch_train_selection_model.py"
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

    for c in feature_cols:
        if c not in df.columns:
            df[c] = 0.0

    X = df[feature_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    df["ml_score"] = model.predict(X)
    df["ml_rank"] = df["ml_score"].rank(ascending=False, method="first").astype(int)

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
