"""快取當月策略所需的每日 OHLC 行情資料。"""

from __future__ import annotations

import argparse
import calendar
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text

# 確保可以從此腳本直接執行時匯入 repo 根目錄
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from train_eps import prepare_data as tp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cache daily quotes by year/month.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 08")
    return parser.parse_args()


def month_date_range(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def add_trading_day_buffer(year: int, month: int, buffer_days: int = 30) -> str:
    end_dt = pd.Timestamp(
        f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}"
    ) + pd.Timedelta(days=buffer_days)
    return end_dt.strftime("%Y-%m-%d")


def get_output_path(output_dir: Path, start_date: str, end_date: str) -> Path:
    s = start_date.replace("-", "")
    e = end_date.replace("-", "")
    filename = f"daily_quotes_{s}_{e}.csv"
    return output_dir / filename


def load_symbols_from_candidates(candidates_path: Path) -> list[str]:
    if not candidates_path.exists():
        return []
    df = pd.read_csv(candidates_path)
    if "symbol" not in df.columns:
        return []
    symbols = (
        df["symbol"]
        .astype(str)
        .str.strip()
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
        .dropna()
        .unique()
        .tolist()
    )
    return sorted(symbols)


def candidate_release_date(year: int, month: int) -> str:
    release_day = 15 if month in {5, 8, 11} else 10
    return f"{year:04d}{month:02d}{release_day:02d}"


def get_candidates_path(base_dir: Path, year: int, month: int) -> Path:
    ymd = candidate_release_date(year, month)
    return (
        base_dir
        / f"{year:04d}"
        / f"{month:02d}"
        / "results_candidates"
        / f"trade_candidates_{ymd}.csv"
    )


def fetch_quotes_from_db(
    conn, symbols: list[str], start_date: str, end_date: str
) -> pd.DataFrame:
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
    if not symbols:
        return pd.DataFrame(columns=keep_cols)

    stmt = text(
        """
        SELECT
          date, symbol, name, market, open, high, low, close, volume,
          value, transactions, change, direction, bid, ask
        FROM daily_quotes
        WHERE symbol IN :symbols
          AND date >= :start_date
          AND date <= :end_date
        """
    ).bindparams(bindparam("symbols", expanding=True))

    t0 = time.perf_counter()
    out = pd.read_sql(
        stmt,
        conn,
        params={
            "symbols": symbols,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    print(
        f"  [db] fetched quotes {start_date}~{end_date}: "
        f"symbols={len(symbols)}, rows={len(out)}, elapsed={time.perf_counter() - t0:.2f}s"
    )

    out = out[[c for c in keep_cols if c in out.columns]].copy()
    out = (
        out.sort_values(["symbol", "date"])
        .drop_duplicates(subset=["symbol", "date"], keep="last")
        .reset_index(drop=True)
    )
    return out


def fetch_and_save_quotes(
    conn, symbols: list[str], start_date: str, end_date: str, output_path: Path
) -> None:
    out = fetch_quotes_from_db(
        conn=conn, symbols=symbols, start_date=start_date, end_date=end_date
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, index=False)
    print(f"  -> saved {len(out)} rows to {output_path}")


def cache_one_period(conn, base_dir: Path, year: int, month: int, label: str) -> None:
    month_s = f"{month:02d}"
    print(f"\n=== [{label}] {year}/{month_s} ===")
    candidates_path = get_candidates_path(base_dir, year, month)
    if not candidates_path.exists():
        raise FileNotFoundError(f"candidates not found: {candidates_path}")
    symbols = load_symbols_from_candidates(candidates_path)
    if not symbols:
        raise RuntimeError(
            f"no valid symbols in candidates: {candidates_path}. "
            "Check whether build_candidates produced only a header row or empty symbols."
        )

    start_date, _ = month_date_range(year, month)
    end_date = add_trading_day_buffer(year, month, buffer_days=30)
    output_dir = base_dir / f"{year:04d}" / month_s / "results_quotes_cache"
    output_path = get_output_path(output_dir, start_date, end_date)
    if output_path.exists():
        print(f"  [skip] cache exists: {output_path}")
        return
    fetch_and_save_quotes(
        conn=conn,
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        output_path=output_path,
    )


def main() -> None:
    args = parse_args()
    year = int(args.year)
    month = int(args.month)
    month_s = f"{month:02d}"
    base_dir = (Path.cwd() / "strategies" / "output").resolve()

    engine = create_engine(tp.get_db_url())
    with engine.connect() as conn:
        cache_one_period(
            conn=conn, base_dir=base_dir, year=year, month=month, label="Current month"
        )

    print("\ncache_daily_quotes done")
    print(f"- year: {year}, month: {month_s}")


if __name__ == "__main__":
    main()
