import argparse
from pathlib import Path

import numpy as np
import pandas as pd


FEATURES = [
    "q2_eps",
    "q2_margin",
    "ly_q3_eps",
    "rev_trend_m8_m7",
    "rev_trend_m9_m8",
    "q2_ocf_ratio",
    "q2_re_ratio",
]
TARGET = "target_eps"
REQUIRED = ["year"] + FEATURES + [TARGET]
KEEP_OPTIONAL = [
    "symbol",
    "name",
    "q2_rev",
    "q2_ni",
    "q2_ocf",
    "q2_retained_earnings",
    "rev_m7",
    "rev_m8",
    "rev_m9",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "analysis" / "v3" / "dataset.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "dataset.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare v3 dataset for analysis_codex.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.source)
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=[TARGET, "year"])

    for col in FEATURES:
        df[col] = df[col].fillna(0)

    keep_cols = [c for c in KEEP_OPTIONAL + REQUIRED if c in df.columns]
    out_df = df[keep_cols].copy()
    out_df["year"] = out_df["year"].astype(int)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)

    print("v3 prepare_data completed")
    print(f"- source: {args.source}")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out_df)}")


if __name__ == "__main__":
    main()

