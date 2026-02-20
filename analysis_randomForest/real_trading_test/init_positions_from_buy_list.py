import argparse
from pathlib import Path

import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize positions.csv from a previous buy list.")
    parser.add_argument("--buy-list", type=Path, required=True)
    parser.add_argument("--execution-date", type=str, required=True, help="Actual executed buy date, e.g. 2025-10-10")
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--max-position-amount", type=float, default=200000.0)
    parser.add_argument("--shares-per-lot", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "positions.csv")
    return parser.parse_args()


def fetch_quotes(api_base: str, market: str, symbols: list[str], date: str) -> pd.DataFrame:
    rows = []
    for s in symbols:
        resp = requests.get(
            f"{api_base}/raw/daily-quotes",
            params={
                "market": market,
                "symbol": s,
                "start_date": date,
                "end_date": date,
                "limit": 5,
                "offset": 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            rows.extend(data)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def calc_shares(entry_open: float, max_position_amount: float, shares_per_lot: int) -> int:
    lot_cost = entry_open * shares_per_lot
    if lot_cost <= max_position_amount:
        return shares_per_lot
    return max(int(max_position_amount // entry_open), 1)


def main() -> None:
    args = parse_args()
    buy_df = pd.read_csv(args.buy_list)
    buy_df["symbol"] = buy_df["symbol"].astype(str).str.strip()
    symbols = sorted(buy_df["symbol"].unique().tolist())

    q = fetch_quotes(args.api_base, args.market, symbols, args.execution_date)
    if q.empty:
        raise SystemExit("No quote rows found for execution date.")
    q["symbol"] = q["symbol"].astype(str).str.strip()
    q["open"] = pd.to_numeric(q["open"], errors="coerce")
    q["high"] = pd.to_numeric(q["high"], errors="coerce")
    q = q.dropna(subset=["open"]).copy()

    merged = buy_df.merge(
        q[["symbol", "open", "high", "date"]],
        on="symbol",
        how="inner",
        suffixes=("", "_q"),
    )
    merged = merged.rename(columns={"open": "entry_price", "high": "highest_high", "date_q": "entry_date"})

    merged["shares"] = merged["entry_price"].apply(
        lambda x: calc_shares(float(x), float(args.max_position_amount), int(args.shares_per_lot))
    )
    merged["capital_used"] = merged["shares"] * merged["entry_price"]
    merged["holding_days"] = 0
    merged["status"] = "open"
    if "predict_target_price" in merged.columns:
        merged["target_price"] = pd.to_numeric(merged["predict_target_price"], errors="coerce")
    else:
        merged["target_price"] = pd.NA

    keep_cols = [
        "symbol",
        "name",
        "industry",
        "entry_date",
        "entry_price",
        "shares",
        "capital_used",
        "highest_high",
        "holding_days",
        "status",
        "target_price",
    ]
    out = merged[[c for c in keep_cols if c in merged.columns]].copy().sort_values("symbol").reset_index(drop=True)
    num_cols = out.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        out[num_cols] = out[num_cols].round(4)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")

    print("positions initialized")
    print(f"- output: {args.output}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
