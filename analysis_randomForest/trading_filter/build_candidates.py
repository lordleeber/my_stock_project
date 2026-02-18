import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PREDICTIONS = Path(__file__).resolve().parents[1] / "v10" / "t3" / "results" / "predictions_year_2025.csv"
DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "v10" / "t3" / "dataset.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "trade_candidates_2025_1013_1120.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trade candidates using live-TTM formulas.")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-ttm-eps", type=float, default=2.0)
    parser.add_argument("--min-volume-lots", type=float, default=500.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pred = pd.read_csv(args.predictions)
    ds = pd.read_csv(args.dataset)

    pred_2025 = pred[pred["fold"] == "year_2025"].copy()
    ds_2025 = ds[ds["year"].astype(int) == 2025].copy()

    use_cols = [
        "symbol",
        "name",
        "industry",
        "ly_q3_eps",
        "prev_q4_eps",
        "q1_eps",
        "q2_eps",
        "q2_eps_official",
    ]
    ds_2025 = ds_2025[[c for c in use_cols if c in ds_2025.columns]].copy()

    df = pred_2025.merge(ds_2025, on="symbol", how="left", suffixes=("", "_ds"))
    df["symbol"] = df["symbol"].astype(str).str.strip()

    # predict_q3_eps = q2_eps + pred_rf_delta
    q2_for_pred = pd.to_numeric(df.get("q2_eps", df.get("q2_eps_official")), errors="coerce")
    pred_delta = pd.to_numeric(df["pred_rf_delta"], errors="coerce")
    df["predict_q3_eps"] = q2_for_pred + pred_delta

    # 你指定的 live 公式
    # ttm_eps_official_live = previous_q3 + prev_q4 + q1 + q2_official
    # ttm_forward_live = prev_q4 + q1 + q2_official + predict_q3_eps
    previous_q3 = pd.to_numeric(df.get("ly_q3_eps"), errors="coerce")
    prev_q4 = pd.to_numeric(df.get("prev_q4_eps"), errors="coerce")
    q1 = pd.to_numeric(df.get("q1_eps"), errors="coerce")
    q2_official = pd.to_numeric(df.get("q2_eps_official"), errors="coerce")

    df["ttm_eps_official_live"] = previous_q3 + prev_q4 + q1 + q2_official
    df["ttm_eps_forward_live"] = prev_q4 + q1 + q2_official + df["predict_q3_eps"]

    df["predict_target_price_live"] = pd.to_numeric(df.get("pe_current"), errors="coerce") * df["predict_q3_eps"]
    df["volume_lots"] = pd.to_numeric(df.get("q3_volume"), errors="coerce") / 1000.0

    ttm_ok = df["ttm_eps_forward_live"] >= float(args.min_ttm_eps)
    vol_ok = df["volume_lots"] >= float(args.min_volume_lots)
    forward_not_worse = df["ttm_eps_forward_live"] >= df["ttm_eps_official_live"]

    out = df[ttm_ok & vol_ok & forward_not_worse].copy()
    out = out.sort_values(["symbol"]).reset_index(drop=True)
    out = out.rename(
        columns={
            "q3_date": "date",
            "q3_close": "close",
            "q3_volume": "volume",
            "predict_target_price_live": "predict_target_price",
        }
    )
    num_cols = out.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        out[num_cols] = out[num_cols].round(2)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print("build_candidates done")
    print(f"- predictions: {args.predictions}")
    print(f"- dataset: {args.dataset}")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
