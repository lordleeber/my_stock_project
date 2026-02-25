"""
cache_daily_quotes.py — Cache daily OHLC quotes for strategy backtesting.

This script fetches daily quotes for TWO purposes:
  1. [Historical training] Last-year same month + last month → used to optimize strategy params
  2. [Current month]       Current {year}/{month}           → used to apply best params

Historical period quotes are cached to their own month directories so optimize_strategy.py
can load them without look-ahead bias.
"""
import argparse
import calendar
from pathlib import Path

import pandas as pd
import requests

API_BASE_DEFAULT = "http://100.103.191.79:8000"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache daily quotes by market/year/month.")
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")
    parser.add_argument("--api-base", type=str, default=API_BASE_DEFAULT)
    parser.add_argument(
        "--skip-historical",
        action="store_true",
        help="Skip caching historical periods (last-year same month + last month). "
             "Only cache the current month.",
    )
    return parser.parse_args()


def month_date_range(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def add_trading_day_buffer(year: int, month: int, buffer_days: int = 30) -> str:
    """
    Return an end_date that is roughly `buffer_days` calendar days after month-end.
    This covers up to 20 trading days of max-hold after the last possible publish date.
    """
    last_day = calendar.monthrange(year, month)[1]
    end_dt = pd.Timestamp(f"{year:04d}-{month:02d}-{last_day:02d}") + pd.Timedelta(days=buffer_days)
    return end_dt.strftime("%Y-%m-%d")


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


def fetch_and_save_quotes(
    api_base: str,
    market: str,
    symbols: list[str],
    start_date: str,
    end_date: str,
    output_path: Path,
) -> None:
    """Fetch quotes for all symbols in [start_date, end_date] and save to output_path."""
    keep_cols = [
        "date", "symbol", "name", "market",
        "open", "high", "low", "close", "volume",
        "value", "transactions", "change", "direction", "bid", "ask",
    ]

    frames: list[pd.DataFrame] = []
    for i, symbol in enumerate(symbols, start=1):
        print(f"  [{i}/{len(symbols)}] fetch {symbol} ({start_date} ~ {end_date})")
        q = fetch_quotes(api_base=api_base, market=market, symbol=symbol,
                         start_date=start_date, end_date=end_date)
        if q.empty:
            continue
        q["symbol"] = q["symbol"].astype(str).str.strip()
        frames.append(q)

    if frames:
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=keep_cols)

    out = out[[c for c in keep_cols if c in out.columns]].copy()
    out = (
        out.sort_values(["symbol", "date"])
        .drop_duplicates(subset=["symbol", "date"], keep="last")
        .reset_index(drop=True)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"  → saved {len(out)} rows to {output_path}")


def get_output_path(base_dir: Path, market: str, year: int, month: int,
                    start_date: str, end_date: str) -> Path:
    s = start_date.replace("-", "")  # YYYYMMDD
    e = end_date.replace("-", "")
    filename = f"daily_quotes_{s}_{e}_{market}.csv"
    return base_dir / market / f"{year:04d}" / f"{month:02d}" / filename


def load_symbols_from_candidates(candidates_path: Path) -> list[str]:
    if not candidates_path.exists():
        return []
    df = pd.read_csv(candidates_path)
    return sorted(df["symbol"].astype(str).str.strip().unique().tolist())


def prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def main() -> None:
    args = parse_args()
    market = args.market
    year = int(args.year)
    month = int(args.month)
    month_s = f"{month:02d}"
    base_dir = (Path.cwd() / "strategies").resolve()

    # ── 1. Current month ──────────────────────────────────────────────────────
    print(f"\n=== [Current month] {year}/{month_s} ===")
    current_candidates_path = base_dir / market / f"{year:04d}" / month_s / "trade_candidates.csv"
    current_symbols = load_symbols_from_candidates(current_candidates_path)
    if not current_candidates_path.exists():
        raise FileNotFoundError(f"candidates not found: {current_candidates_path}")

    cur_start, cur_end = month_date_range(year, month)
    # Add 30-day buffer so 20-trading-day holds after month-end are covered
    cur_end_buffered = add_trading_day_buffer(year, month, buffer_days=30)
    cur_output = get_output_path(base_dir, market, year, month, cur_start, cur_end_buffered)

    fetch_and_save_quotes(
        api_base=args.api_base,
        market=market,
        symbols=current_symbols,
        start_date=cur_start,
        end_date=cur_end_buffered,
        output_path=cur_output,
    )

    if args.skip_historical:
        print("\n[skip-historical] Skipping historical period caching.")
        return

    # ── 2. Historical period A: Last-year same month ──────────────────────────
    ly_year, ly_month = year - 1, month
    ly_month_s = f"{ly_month:02d}"
    print(f"\n=== [Historical A] Last-year same month: {ly_year}/{ly_month_s} ===")
    ly_candidates_path = base_dir / market / f"{ly_year:04d}" / ly_month_s / "trade_candidates.csv"
    ly_symbols = load_symbols_from_candidates(ly_candidates_path)

    if not ly_symbols:
        print(f"  [warn] No candidates found at {ly_candidates_path}. Skipping period A.")
    else:
        ly_start, _ = month_date_range(ly_year, ly_month)
        ly_end_buffered = add_trading_day_buffer(ly_year, ly_month, buffer_days=30)
        ly_output = get_output_path(base_dir, market, ly_year, ly_month, ly_start, ly_end_buffered)
        fetch_and_save_quotes(
            api_base=args.api_base,
            market=market,
            symbols=ly_symbols,
            start_date=ly_start,
            end_date=ly_end_buffered,
            output_path=ly_output,
        )

    # ── 3. Historical period B: Last month ────────────────────────────────────
    lm_year, lm_month = prev_month(year, month)
    lm_month_s = f"{lm_month:02d}"
    print(f"\n=== [Historical B] Last month: {lm_year}/{lm_month_s} ===")
    lm_candidates_path = base_dir / market / f"{lm_year:04d}" / lm_month_s / "trade_candidates.csv"
    lm_symbols = load_symbols_from_candidates(lm_candidates_path)

    if not lm_symbols:
        print(f"  [warn] No candidates found at {lm_candidates_path}. Skipping period B.")
    else:
        lm_start, _ = month_date_range(lm_year, lm_month)
        lm_end_buffered = add_trading_day_buffer(lm_year, lm_month, buffer_days=30)
        lm_output = get_output_path(base_dir, market, lm_year, lm_month, lm_start, lm_end_buffered)
        fetch_and_save_quotes(
            api_base=args.api_base,
            market=market,
            symbols=lm_symbols,
            start_date=lm_start,
            end_date=lm_end_buffered,
            output_path=lm_output,
        )

    print("\ncache_daily_quotes done")
    print(f"- market: {market}, year: {year}, month: {month_s}")


if __name__ == "__main__":
    main()
