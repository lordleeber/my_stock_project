from __future__ import annotations

import argparse
import calendar
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtester.engine import BacktestConfig
from backtester.scenario_revenue_window import run_revenue_window_backtest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Event-driven monthly backtest runner")
    parser.add_argument("--market", type=str, default="sii", choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 09")

    parser.add_argument("--max-position-amount", type=float, default=200000.0)
    parser.add_argument("--shares-per-lot", type=int, default=1000)
    parser.add_argument("--stop-loss-pct", type=float, default=0.11)
    parser.add_argument("--take-profit-pct", type=float, default=None)
    parser.add_argument("--trailing-stop-pct", type=float, default=0.06)
    parser.add_argument("--max-hold-days", type=int, default=None)
    parser.add_argument("--min-score", type=float, default=None)
    return parser.parse_args()


def month_dates(year: int, month: int) -> tuple[str, str]:
    last_day = calendar.monthrange(year, month)[1]
    start_date = f"{year:04d}-{month:02d}-01"
    end_date = f"{year:04d}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def main() -> None:
    args = parse_args()
    market = args.market
    year = int(args.year)
    month = int(args.month)
    month_s = f"{month:02d}"
    start_date, end_date = month_dates(year, month)

    yyyymm01 = f"{year:04d}{month:02d}01"
    yyyymmdd = f"{year:04d}{month:02d}{calendar.monthrange(year, month)[1]:02d}"

    ann_path = (Path.cwd() / "backtester" / market / f"{year:04d}" / month_s / "announcements.csv").resolve()
    quotes_path = (
        Path.cwd() / "strategies" / market / f"{year:04d}" / month_s / f"daily_quotes_{yyyymm01}_{yyyymmdd}_{market}.csv"
    ).resolve()
    outdir = (Path.cwd() / "backtester" / market / f"{year:04d}" / month_s / "results").resolve()

    if not ann_path.exists():
        raise FileNotFoundError(f"announcements not found: {ann_path}")
    if not quotes_path.exists():
        raise FileNotFoundError(f"quotes not found: {quotes_path}")

    outdir.mkdir(parents=True, exist_ok=True)

    ann = pd.read_csv(ann_path)
    quotes = pd.read_csv(quotes_path)

    cfg = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        force_exit_date=end_date,
        no_pyramiding=True,
        max_position_amount=float(args.max_position_amount),
        shares_per_lot=int(args.shares_per_lot),
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        trailing_stop_pct=args.trailing_stop_pct,
        max_hold_days=args.max_hold_days,
    )

    (trades_df, positions_df, summary), signals_df = run_revenue_window_backtest(
        announcements_df=ann,
        quotes_df=quotes,
        cfg=cfg,
        window_start=start_date,
        window_end=end_date,
        min_score=args.min_score,
    )

    signals_path = outdir / "signals.csv"
    trades_path = outdir / "trades.csv"
    positions_path = outdir / "positions_end.csv"
    summary_path = outdir / "summary.json"

    signals_df.to_csv(signals_path, index=False, encoding="utf-8-sig")
    trades_df.to_csv(trades_path, index=False, encoding="utf-8-sig")
    positions_df.to_csv(positions_path, index=False, encoding="utf-8-sig")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("backtest done")
    print(f"- market: {market}")
    print(f"- year: {year}")
    print(f"- month: {month_s}")
    print(f"- start_date: {start_date}")
    print(f"- end_date: {end_date}")
    print(f"- announcements: {ann_path}")
    print(f"- quotes: {quotes_path}")
    print(f"- outdir: {outdir}")
    print(f"- signals: {signals_path}")
    print(f"- trades: {trades_path}")
    print(f"- positions: {positions_path}")
    print(f"- summary: {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
