import argparse
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd

from shared_config import target_quarter_for_playbook

ROOT_DIR = Path(__file__).resolve().parent.parent

EXCLUDE_COLUMNS = {
    "symbol",
    "name",
    "industry",
    "year",
    "anchor_quarter",
    "target_eps",
    "delta_eps",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict EPS delta and write predictions_results.csv to models_eps/"
    )
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 10")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    year = int(args.year)
    month = str(args.month).zfill(2)
    # January playbook predicts previous year's Q4 — step1 emits rows with
    # year=target_year, so step4 must filter by target_year, not execution year.
    target_year, qnum = target_quarter_for_playbook(year, month)

    input_path = (
        ROOT_DIR
        / "train_eps"
        / "output"
        / f"{year:04d}"
        / month
        / "dataset_evaluate.csv"
    ).resolve()
    models_dir = (ROOT_DIR / "models_eps" / f"{year:04d}" / month).resolve()
    output_path = (models_dir / "predictions_results.csv").resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"dataset_evaluate.csv not found: {input_path}")

    # 選擇 MAE 最低的 pkl（格式：{timestamp}_{mae:.3f}.pkl）。
    pkl_pattern = re.compile(r"^\d{14}_(\d+\.\d+)\.pkl$")
    candidates = []
    for p in models_dir.glob("*.pkl"):
        m = pkl_pattern.match(p.name)
        if m:
            candidates.append((float(m.group(1)), p))
    if not candidates:
        raise FileNotFoundError(
            f"No timestamped model pkl found in {models_dir}\n"
            f"Run: venv/bin/python3 train_eps/train.py --year {year} --month {month}"
        )
    model_path = min(candidates, key=lambda x: x[0])[1]

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    df = pd.read_csv(input_path).replace([np.inf, -np.inf], np.nan)

    # 嚴格檢查：dataset 必須包含本次 playbook 要 predict 的 year（= args.year）。
    # 過去版本若資料缺 year，會 silent fallback 到 max(year)，導致 May 2026 用 2025
    # 的 row 預測 2025Q2 而非 2026Q2，整份 predictions 錯一年。
    y = pd.to_numeric(df["year"], errors="coerce")
    valid_years = set(int(v) for v in y.dropna().astype(int).unique())
    if not valid_years:
        raise RuntimeError(f"No valid year values found in: {input_path}")
    if target_year not in valid_years:
        raise RuntimeError(
            f"dataset_evaluate.csv does not contain rows for year={target_year} "
            f"(found years: {sorted(valid_years)}). Re-run step1 prepare_data "
            f"for {year}/{month} — most likely upstream XBRL data for anchor "
            f"quarter is incomplete."
        )
    df = df[y == target_year].copy()

    if hasattr(model, "feature_names_in_"):
        feature_cols = list(model.feature_names_in_)
    else:
        feature_cols = [c for c in df.columns if c not in EXCLUDE_COLUMNS]

    # 缺欄位 = 上游 schema 不一致，直接報錯，不要 silent 補 0。
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"dataset_evaluate.csv missing feature columns expected by model: {missing}"
        )
    # 各欄 NaN 不填 0：LightGBM 原生處理 NaN，silent fillna(0) 會把缺值當實際 0
    # 餵進模型，污染預測。

    pred_delta = model.predict(df[feature_cols])

    out = df[["year", "symbol", "name", "industry"]].copy()
    if "target_eps" in df.columns:
        out["y_true"] = df["target_eps"]
    out["pred_lgb_delta"] = pred_delta
    # target_quarter / trained_at_month / model_pkl 是 metadata 欄位，
    # 標示「這份 predictions 是在哪個 playbook 跑出來、預測哪個季度、用哪個 pkl」，
    # 取代原本的 fold 欄（與 year 同義冗餘）。
    out["target_quarter"] = out["year"].astype(int).astype(str) + f"Q{qnum}"
    if "anchor_quarter" in df.columns:
        out["anchor_quarter"] = df["anchor_quarter"].values
    out["trained_at_month"] = f"{year:04d}/{month}"
    out["model_pkl"] = model_path.name

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print("predict_and_publish completed")
    print(f"- year: {year}")
    print(f"- month: {month}")
    print(f"- model: {model_path}")
    print(f"- input: {input_path}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
