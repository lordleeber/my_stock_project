#!/usr/bin/env python3
import argparse
import csv
import os
from datetime import datetime, timedelta


RAW_DIR = "data/raw/daily_quotes"


def parse_date(s):
    return datetime.strptime(s, "%Y%m%d")


def list_dates(start, end):
    curr = start
    while curr <= end:
        yield curr
        curr += timedelta(days=1)


def load_close_map(date_str, market):
    new_path = os.path.join(RAW_DIR, date_str[:4], date_str, f"{market}.csv")
    old_path = os.path.join(RAW_DIR, f"date={date_str}", f"{market}.csv")
    path = new_path if os.path.exists(new_path) else old_path
    if not os.path.exists(path):
        return {}
    close_map = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].isdigit():
                continue
            if len(row) < 9:
                continue
            symbol = row[0].strip()
            name = row[1].strip()
            close = row[8].strip()
            if close in ("", "--"):
                continue
            try:
                close_val = float(close.replace(",", ""))
            except ValueError:
                continue
            close_map[symbol] = (name, close_val)
    return close_map


def main():
    parser = argparse.ArgumentParser(description="Check raw daily quotes anomalies.")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--market", default="sii", choices=["sii", "otc"])
    parser.add_argument("--pct", type=float, default=0.11, help="Threshold for daily change (e.g. 0.11)")
    parser.add_argument("--revert", type=float, default=0.7, help="Reversion factor (next day close < peak * revert)")
    parser.add_argument("--limit", type=int, default=200, help="Max anomalies to print")
    parser.add_argument("--exclude-etf", action="store_true", help="Exclude ETF/ETN (symbols starting with 00)")
    args = parser.parse_args()

    start = parse_date(args.start)
    end = parse_date(args.end)

    anomalies = []

    for dt in list_dates(start, end):
        date_str = dt.strftime("%Y%m%d")
        prev_str = (dt - timedelta(days=1)).strftime("%Y%m%d")
        next_str = (dt + timedelta(days=1)).strftime("%Y%m%d")

        curr = load_close_map(date_str, args.market)
        prev = load_close_map(prev_str, args.market)
        next_day = load_close_map(next_str, args.market)
        if not curr or not prev:
            continue

        for symbol, (name, close_curr) in curr.items():
            if args.exclude_etf and symbol.startswith("00"):
                continue
            if symbol not in prev:
                continue
            close_prev = prev[symbol][1]
            if close_prev == 0:
                continue
            pct_change = (close_curr - close_prev) / close_prev
            if abs(pct_change) <= args.pct:
                continue

            close_next = None
            if symbol in next_day:
                close_next = next_day[symbol][1]

            # Reversion check: next day falls back to a % of spike
            reverted = False
            if close_next is not None:
                if close_curr > close_prev:
                    reverted = close_next < close_curr * args.revert
                else:
                    reverted = close_next > close_curr / args.revert

            anomalies.append({
                "symbol": symbol,
                "name": name,
                "date": date_str,
                "close_prev": close_prev,
                "close_curr": close_curr,
                "close_next": close_next,
                "pct_change": pct_change,
                "reverted": reverted,
            })

    anomalies.sort(key=lambda x: abs(x["pct_change"]), reverse=True)

    print(f"Found {len(anomalies)} anomalies in {args.market} from {args.start} to {args.end}")
    for i, a in enumerate(anomalies[: args.limit]):
        next_str = "--" if a["close_next"] is None else f"{a['close_next']:.2f}"
        print(
            f"{i+1:03d} {a['symbol']} {a['name']} {a['date']} "
            f"prev={a['close_prev']:.2f} curr={a['close_curr']:.2f} "
            f"next={next_str} "
            f"chg={a['pct_change']*100:.2f}% reverted={a['reverted']}"
        )


if __name__ == "__main__":
    main()
