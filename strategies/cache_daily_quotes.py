import argparse
import calendar
from pathlib import Path

import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache daily quotes by market/year/month.")
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--api-base", type=str, default="http://100.103.191.79:8000")
    return parser.parse_args()


def month_date_range(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def fetch_quotes(api_base: str, market: str, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    url = f"{api_base.rstrip('/')}/raw/daily-quotes"
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
    market = args.market
    year = int(args.year)
    month = int(args.month)
    month_s = f"{month:02d}"

    default_candidates = (Path.cwd() / "strategies" / market / f"{year:04d}" / month_s / "trade_candidates.csv").resolve()
    start_default, end_default = month_date_range(year, month)

    start_date = start_default
    end_date = end_default

    yyyymm01 = f"{year:04d}{month:02d}01"
    yyyymmdd = f"{year:04d}{month:02d}{calendar.monthrange(year, month)[1]:02d}"
    default_output = (
        Path.cwd()
        / "strategies"
        / market
        / f"{year:04d}"
        / month_s
        / f"daily_quotes_{yyyymm01}_{yyyymmdd}_{market}.csv"
    ).resolve()

    candidates_path = default_candidates
    output_path = default_output
    if not candidates_path.exists():
        raise FileNotFoundError(f"candidates not found: {candidates_path}")

    cand = pd.read_csv(candidates_path)
    symbols = sorted(cand["symbol"].astype(str).str.strip().unique().tolist())

    frames: list[pd.DataFrame] = []
    for i, symbol in enumerate(symbols, start=1):
        print(f"[{i}/{len(symbols)}] fetch {symbol}")
        q = fetch_quotes(
            api_base=args.api_base,
            market=market,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        if q.empty:
            continue
        q["symbol"] = q["symbol"].astype(str).str.strip()
        frames.append(q)

    if frames:
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=["date", "symbol", "name", "market", "open", "high", "low", "close", "volume"])

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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)

    print("cache daily quotes done")
    print(f"- market: {market}")
    print(f"- year: {year}")
    print(f"- month: {month_s}")
    print(f"- start_date: {start_date}")
    print(f"- end_date: {end_date}")
    print(f"- candidates: {candidates_path}")
    print(f"- output: {output_path}")
    print(f"- symbols: {len(symbols)}")
    print(f"- rows: {len(out)}")


if __name__ == "__main__":
    main()
