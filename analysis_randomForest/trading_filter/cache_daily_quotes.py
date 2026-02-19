import argparse
from pathlib import Path

import pandas as pd
import requests


DEFAULT_CANDIDATES = Path(__file__).resolve().parent / "trade_candidates_2025_1013_1120.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "daily_quotes_20251013_1120_sii.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="下載並快取交易回測用日線資料。")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--start-date", type=str, default="2025-10-13")
    parser.add_argument("--end-date", type=str, default="2025-11-20")
    parser.add_argument("--market", type=str, default="sii")
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    return parser.parse_args()


def fetch_quotes(api_base: str, market: str, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = f"{api_base}/raw/daily-quotes"
    params = {
        "market": market,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "limit": 500,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


def main() -> None:
    args = parse_args()

    cand = pd.read_csv(args.candidates)
    symbols = sorted(cand["symbol"].astype(str).str.strip().unique().tolist())

    frames = []
    for i, symbol in enumerate(symbols, start=1):
        print(f"[{i}/{len(symbols)}] fetch {symbol}")
        q = fetch_quotes(
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
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=["date", "symbol", "name", "market", "open", "high", "low", "close", "volume"])

    # 固定欄位順序，方便後續腳本直接讀取
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
    out = out[[c for c in keep_cols if c in out.columns]].copy()
    out = out.sort_values(["symbol", "date"]).drop_duplicates(subset=["symbol", "date"], keep="last").reset_index(drop=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)

    print("cache daily quotes done")
    print(f"- candidates: {args.candidates}")
    print(f"- output: {args.output}")
    print(f"- symbols: {len(symbols)}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
