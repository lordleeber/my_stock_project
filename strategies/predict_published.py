import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict EPS with published model in models_eps/<year>/<month>")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--month", type=str, required=True, help="e.g. 10")
    parser.add_argument("--input", type=Path, default=None, help="default: strategies/output/<year>/<month>/dataset_model_input.csv")
    parser.add_argument("--data-root", type=Path, default=Path("strategies/output"))
    parser.add_argument("--models-root", type=Path, default=Path("models_eps"))
    return parser.parse_args()


def add_cross_section_quantiles(df: pd.DataFrame, z_cols: list[str]) -> None:
    group_cols = ["year", "industry"] if "industry" in df.columns else ["year"]
    for z_col in z_cols:
        quantile_col = z_col.replace("_z", "_quantile")
        ranks = df.groupby(group_cols)[z_col].rank(method="average", pct=True).fillna(0.5)
        df[quantile_col] = np.ceil(ranks * 10.0).clip(1.0, 10.0) / 10.0


def main() -> None:
    args = parse_args()
    year = int(args.year)
    month = args.month.zfill(2)

    data_root = args.data_root if args.data_root.is_absolute() else (Path.cwd() / args.data_root).resolve()
    models_root = args.models_root if args.models_root.is_absolute() else (Path.cwd() / args.models_root).resolve()

    month_dir = (data_root / f"{year:04d}" / month).resolve()
    model_path = models_root / f"{year:04d}" / month / "model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"model.pkl not found: {model_path}")

    input_path = args.input if args.input else (month_dir / "dataset_model_input.csv")
    output_path = (Path.cwd() / "strategies" / "output" / f"{year:04d}" / month / "predictions_published.csv").resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")

    with open(model_path, "rb") as f:
        model = pickle.load(f)

    df = pd.read_csv(input_path).replace([np.inf, -np.inf], np.nan)

    # 與 train/evaluate 對齊：統一生成 quantile 特徵
    z_cols = [c for c in df.columns if c.endswith("_z")]
    add_cross_section_quantiles(df, z_cols)

    if hasattr(model, "feature_names_in_"):
        feature_cols = list(model.feature_names_in_)
    else:
        exclude = {
            "symbol",
            "name",
            "industry",
            "q3_date",
            "q3_close",
            "q3_volume",
            "pe_current",
            "prev_q4_eps",
            "q1_eps",
            "q2_eps_official",
            "ttm_eps_official",
            "feature_cutoff_date",
            "year",
            "target_eps",
            "delta_eps",
        }
        feature_cols = [c for c in df.columns if c not in exclude]

    for c in feature_cols:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = df[c].fillna(0.0)

    pred_delta = model.predict(df[feature_cols])

    # Output schema aligns to evaluate predictions core fields.
    out = pd.DataFrame()
    for c in [
        "year",
        "symbol",
        "name",
        "industry",
        "feature_cutoff_date",
        "q3_date",
        "q3_close",
        "q3_volume",
        "pe_current",
        "ttm_eps_official",
    ]:
        if c in df.columns:
            out[c] = df[c]
    if "target_eps" in df.columns:
        out["y_true"] = df["target_eps"]
    out["pred_lgb_delta"] = pred_delta
    if "year" in out.columns:
        out["fold"] = "year_" + out["year"].astype(int).astype(str)
    else:
        out["fold"] = "year_unknown"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print("prediction completed")
    print(f"- year: {year}")
    print(f"- month: {month}")
    print(f"- model: {model_path}")
    print(f"- input: {input_path}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
