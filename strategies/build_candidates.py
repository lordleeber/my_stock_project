import argparse
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trade candidates using market/year/month paths.")
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--min-ttm-eps", type=float, default=2.0)
    parser.add_argument("--min-volume-lots", type=float, default=500.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    market = args.market
    year = int(args.year)
    month = str(args.month).zfill(2)

    default_pred = (Path.cwd() / "strategies" / market / f"{year:04d}" / month / "predictions_published.csv").resolve()
    default_ds = (Path.cwd() / "train_eps" / market / f"{year:04d}" / month / "dataset_evaluate.csv").resolve()
    output_path = (Path.cwd() / "strategies" / market / f"{year:04d}" / month / "trade_candidates.csv").resolve()

    pred_path = default_pred
    ds_path = default_ds
    if not pred_path.exists():
        raise FileNotFoundError(f"predictions not found: {pred_path}")
    if not ds_path.exists():
        raise FileNotFoundError(f"dataset not found: {ds_path}")

    pred = pd.read_csv(pred_path)
    ds = pd.read_csv(ds_path)

    pred_year = pred[pred["fold"] == f"year_{year}"].copy()
    ds_year = ds[ds["year"].astype(int) == year].copy()

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
    ds_year = ds_year[[c for c in use_cols if c in ds_year.columns]].copy()

    df = pred_year.merge(ds_year, on="symbol", how="left", suffixes=("", "_ds"))
    df["symbol"] = df["symbol"].astype(str).str.strip()

    q2_for_pred = pd.to_numeric(df.get("q2_eps", df.get("q2_eps_official")), errors="coerce")
    pred_delta = pd.to_numeric(df["pred_rf_delta"], errors="coerce")
    df["predict_q3_eps"] = q2_for_pred + pred_delta

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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print("build_candidates done")
    print(f"- market: {market}")
    print(f"- year: {year}")
    print(f"- month: {month}")
    print(f"- predictions: {pred_path}")
    print(f"- dataset: {ds_path}")
    print(f"- output: {output_path}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
