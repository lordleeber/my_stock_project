import argparse
import pickle
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent

EXCLUDE_COLUMNS = {"symbol", "name", "industry", "year", "target_eps", "delta_eps"}


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

    # Pick the pkl with the lowest MAE (format: {timestamp}_{mae:.3f}.pkl).
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

    # Keep only max-year rows.
    y = pd.to_numeric(df["year"], errors="coerce")
    valid_years = y.dropna().astype(int)
    if valid_years.empty:
        raise RuntimeError(f"No valid year values found in: {input_path}")
    selected_year = int(valid_years.max())
    df = df[y == selected_year].copy()

    if hasattr(model, "feature_names_in_"):
        feature_cols = list(model.feature_names_in_)
    else:
        feature_cols = [c for c in df.columns if c not in EXCLUDE_COLUMNS]

    for c in feature_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)

    pred_delta = model.predict(df[feature_cols])

    out = df[["year", "symbol", "name", "industry"]].copy()
    if "target_eps" in df.columns:
        out["y_true"] = df["target_eps"]
    out["pred_lgb_delta"] = pred_delta
    out["fold"] = "year_" + out["year"].astype(int).astype(str)

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
