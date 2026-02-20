import argparse
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_PREDICTIONS = ROOT / "analysis_randomForest" / "v10" / "t3" / "results" / "predictions_year_2025.csv"
DEFAULT_DATASET = ROOT / "analysis_randomForest" / "v10" / "t3" / "dataset.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "trade_candidates_2025_1009.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build real trading candidates on 2025-10-09 using DB daily data.")
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    parser.add_argument("--date", type=str, default="2025-10-09")
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-ttm-eps", type=float, default=2.0)
    parser.add_argument("--min-volume-lots", type=float, default=500.0)
    return parser.parse_args()


def fetch_all_rows(api_base: str, endpoint: str, params: dict) -> pd.DataFrame:
    url = f"{api_base}{endpoint}"
    rows = []
    offset = 0
    limit = 5000
    while True:
        q = dict(params)
        q["limit"] = limit
        q["offset"] = offset
        resp = requests.get(url, params=q, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        rows.extend(data)
        if len(data) < limit:
            break
        offset += limit
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()

    pred = pd.read_csv(args.predictions)
    ds = pd.read_csv(args.dataset)
    pred_2025 = pred[pred["fold"] == "year_2025"].copy()
    pred_2025["symbol"] = pred_2025["symbol"].astype(str).str.strip()

    ds_2025 = ds[ds["year"].astype(int) == 2025].copy()
    ds_2025["symbol"] = ds_2025["symbol"].astype(str).str.strip()
    keep_cols = [
        "symbol",
        "name",
        "industry",
        "ly_q3_eps",
        "prev_q4_eps",
        "q1_eps",
        "q2_eps",
        "q2_eps_official",
    ]
    ds_2025 = ds_2025[[c for c in keep_cols if c in ds_2025.columns]].copy()

    date_params = {
        "start_date": args.date,
        "end_date": args.date,
        "market": args.market,
    }
    dq = fetch_all_rows(args.api_base, "/raw/daily-quotes", date_params)
    pe = fetch_all_rows(args.api_base, "/raw/pe-ratio", date_params)

    if dq.empty:
        raise SystemExit("No daily quotes fetched from DB API.")
    if pe.empty:
        print("Warning: no PE rows fetched; pe_current will be missing for many symbols.")

    dq["symbol"] = dq["symbol"].astype(str).str.strip()
    dq = dq.rename(columns={"date": "trade_date", "close": "close", "volume": "volume"})
    dq = dq[["trade_date", "symbol", "name", "market", "close", "volume"]].copy()

    pe["symbol"] = pe["symbol"].astype(str).str.strip()
    pe = pe.rename(columns={"pe_ratio": "pe_current"})
    pe = pe[["symbol", "pe_current"]].copy()

    df = pred_2025.merge(ds_2025, on="symbol", how="left", suffixes=("", "_ds"))
    df = df.merge(dq, on="symbol", how="left", suffixes=("", "_dq"))
    df = df.merge(pe, on="symbol", how="left", suffixes=("", "_dbpe"))

    # 優先使用 DB 當日 pe_ratio，若缺值再退回模型檔中的 pe_current。
    pe_db_col = "pe_current_dbpe" if "pe_current_dbpe" in df.columns else ("pe_current_y" if "pe_current_y" in df.columns else None)
    pe_src_col = "pe_current" if "pe_current" in df.columns else ("pe_current_x" if "pe_current_x" in df.columns else None)
    if pe_db_col is not None:
        if pe_src_col is not None and pe_src_col != pe_db_col:
            df["pe_current"] = pd.to_numeric(df[pe_db_col], errors="coerce").combine_first(
                pd.to_numeric(df[pe_src_col], errors="coerce")
            )
        else:
            df["pe_current"] = pd.to_numeric(df[pe_db_col], errors="coerce")

    q2_for_pred = pd.to_numeric(df.get("q2_eps", df.get("q2_eps_official")), errors="coerce")
    pred_delta = pd.to_numeric(df["pred_rf_delta"], errors="coerce")
    df["predict_q3_eps"] = q2_for_pred + pred_delta

    previous_q3 = pd.to_numeric(df.get("ly_q3_eps"), errors="coerce")
    prev_q4 = pd.to_numeric(df.get("prev_q4_eps"), errors="coerce")
    q1 = pd.to_numeric(df.get("q1_eps"), errors="coerce")
    q2_official = pd.to_numeric(df.get("q2_eps_official"), errors="coerce")
    df["ttm_eps_official_live"] = previous_q3 + prev_q4 + q1 + q2_official
    df["ttm_eps_forward_live"] = prev_q4 + q1 + q2_official + df["predict_q3_eps"]

    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    df["pe_current"] = pd.to_numeric(df["pe_current"], errors="coerce")
    df["predict_target_price"] = df["pe_current"] * df["predict_q3_eps"]
    df["volume_lots"] = df["volume"] / 1000.0

    ttm_ok = df["ttm_eps_forward_live"] >= float(args.min_ttm_eps)
    vol_ok = df["volume_lots"] >= float(args.min_volume_lots)
    forward_not_worse = df["ttm_eps_forward_live"] >= df["ttm_eps_official_live"]
    has_price = df["close"].notna() & df["pe_current"].notna()

    out = df[ttm_ok & vol_ok & forward_not_worse & has_price].copy()
    out = out.sort_values(["symbol"]).reset_index(drop=True)
    out = out.rename(columns={"trade_date": "date"})

    num_cols = out.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        out[num_cols] = out[num_cols].round(2)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")

    print("build real trading candidates done")
    print(f"- date: {args.date}")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
