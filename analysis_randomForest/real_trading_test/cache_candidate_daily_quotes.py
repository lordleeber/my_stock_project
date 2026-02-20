import argparse
from pathlib import Path

import pandas as pd
import requests


DEFAULT_CANDIDATES = Path(__file__).resolve().parents[1] / "trading_filter" / "trade_candidates_2025_1013_1120.csv"
DEFAULT_OUTDIR = Path(__file__).resolve().parent / "daily_cache_20251009_1120"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache candidate daily quotes and split one CSV per day.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--start-date", type=str, default="2025-10-09")
    parser.add_argument("--end-date", type=str, default="2025-11-20")
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    return parser.parse_args()


def fetch_symbol_quotes(api_base: str, market: str, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = f"{api_base}/raw/daily-quotes"
    params = {
        "market": market,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "limit": 5000,
        "offset": 0,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return pd.DataFrame(data) if data else pd.DataFrame()


def main() -> None:
    args = parse_args()
    cand = pd.read_csv(args.candidates)
    symbols = sorted(cand["symbol"].astype(str).str.strip().unique().tolist())

    frames = []
    for i, symbol in enumerate(symbols, start=1):
        print(f"[{i}/{len(symbols)}] fetch {symbol}")
        q = fetch_symbol_quotes(
            api_base=args.api_base,
            market=args.market,
            symbol=symbol,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        if q.empty:
            continue
        q["symbol"] = q["symbol"].astype(str).str.strip()
        frames.append(q)

    if frames:
        all_df = pd.concat(frames, ignore_index=True)
    else:
        all_df = pd.DataFrame(columns=["date", "symbol", "name", "market", "open", "high", "low", "close", "volume"])

    keep_cols = [
        "date",
        "symbol",
        "name",
        "market",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "value",
        "transactions",
        "change",
        "direction",
        "bid",
        "ask",
    ]
    all_df = all_df[[c for c in keep_cols if c in all_df.columns]].copy()
    all_df = all_df.sort_values(["date", "symbol"]).drop_duplicates(subset=["date", "symbol"], keep="last").reset_index(drop=True)

    args.outdir.mkdir(parents=True, exist_ok=True)
    all_path = args.outdir / "all_quotes.csv"
    all_df.to_csv(all_path, index=False, encoding="utf-8-sig")

    if not all_df.empty:
        for d, g in all_df.groupby("date"):
            date_tag = str(d).replace("-", "")
            out_path = args.outdir / f"quotes_{date_tag}.csv"
            g.sort_values("symbol").to_csv(out_path, index=False, encoding="utf-8-sig")

    print("cache done")
    print(f"- candidates: {args.candidates}")
    print(f"- symbols: {len(symbols)}")
    print(f"- all_rows: {len(all_df)}")
    print(f"- outdir: {args.outdir}")
    print(f"- all_csv: {all_path}")


if __name__ == "__main__":
    main()
