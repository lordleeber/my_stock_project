from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtester.data_loader import estimate_quote_window, fetch_quotes_from_db, load_candidates
from backtester.simulator import CostConfig, aggregate_monthly, build_equity_curve, simulate_one
from backtester.utils import output_dir, parse_strategy_json, resolve_best_strategy_path, resolve_candidates_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one-month backtest from strategy outputs.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--tax-rate", type=float, default=0.003)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--position-amount", type=float, default=100000.0)
    return parser.parse_args()


def run_month(year: int, month: int, cost_cfg: CostConfig, position_amount: float = 100000.0) -> dict:
    strategies_out = (Path.cwd() / "strategies" / "output").resolve()
    backtester_out = (Path.cwd() / "backtester" / "output").resolve()

    candidates_path = resolve_candidates_path(strategies_out, year, month)
    strategy_path = resolve_best_strategy_path(strategies_out, year, month)
    out_dir = output_dir(backtester_out, year, month)
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_candidates(candidates_path)
    parsed = parse_strategy_json(strategy_path)

    max_hold_days = int(parsed.exit_rule.get("max_hold_days", 20))
    start_date, end_date = estimate_quote_window(candidates, max_hold_days=max_hold_days)
    symbols = sorted(candidates["symbol"].astype(str).str.strip().unique().tolist())
    quotes = fetch_quotes_from_db(symbols=symbols, start_date=start_date, end_date=end_date)

    if quotes.empty:
        raise RuntimeError(f"no quotes fetched from DB for {year}-{month:02d}, symbols={len(symbols)}")

    rows = []
    for _, row in candidates.iterrows():
        rows.append(
            simulate_one(
                row=row,
                quote_df=quotes,
                strategy_name=parsed.strategy_name,
                entry_rule=parsed.entry_rule,
                take_profit_rule=parsed.take_profit_rule,
                exit_rule=parsed.exit_rule,
                cost_cfg=cost_cfg,
                position_cfg={"shares_per_lot": 1000, "max_position_amount": position_amount},
            )
        )
    trades = pd.DataFrame(rows)

    # Enforce look-ahead safety.
    violations = trades[trades["status"] == "lookahead_violation"].copy()
    if "actual_entry_date" in trades.columns and "signal_entry_date" in trades.columns:
        date_cmp = trades.dropna(subset=["actual_entry_date", "signal_entry_date"]).copy()
        if not date_cmp.empty:
            bad = date_cmp[pd.to_datetime(date_cmp["actual_entry_date"]) < pd.to_datetime(date_cmp["signal_entry_date"])]
            if not bad.empty:
                violations = pd.concat([violations, bad], ignore_index=True)

    trades_out = out_dir / "trades.csv"
    monthly_out = out_dir / "monthly_summary.csv"
    equity_out = out_dir / "equity_curve.csv"
    summary_out = out_dir / "summary.json"

    num_cols = trades.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        trades[num_cols] = trades[num_cols].round(6)
    trades.to_csv(trades_out, index=False, encoding="utf-8-sig")

    monthly = aggregate_monthly(trades)
    monthly.to_csv(monthly_out, index=False, encoding="utf-8-sig")

    equity = build_equity_curve(trades)
    equity.to_csv(equity_out, index=False, encoding="utf-8-sig")

    summary = {
        "year": year,
        "month": f"{month:02d}",
        "candidates_path": str(candidates_path),
        "best_strategy_path": str(strategy_path),
        "quotes_start_date": start_date,
        "quotes_end_date": end_date,
        "quotes_rows": int(len(quotes)),
        "symbols_count": int(len(symbols)),
        "lookahead_violation_count": int(len(violations)),
        "lookahead_passed": int(len(violations)) == 0,
        "cost_config": {
            "commission_rate": cost_cfg.commission_rate,
            "tax_rate": cost_cfg.tax_rate,
            "slippage_rate": cost_cfg.slippage_rate,
        },
        "position_amount": position_amount,
    }
    summary_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(violations) > 0:
        raise RuntimeError(f"look-ahead violation found: {len(violations)}")

    return {
        "output_dir": str(out_dir),
        "trades": str(trades_out),
        "monthly_summary": str(monthly_out),
        "equity_curve": str(equity_out),
        "summary": str(summary_out),
    }


def main() -> None:
    args = parse_args()
    result = run_month(
        year=args.year,
        month=args.month,
        cost_cfg=CostConfig(
            commission_rate=args.commission_rate,
            tax_rate=args.tax_rate,
            slippage_rate=args.slippage_rate,
        ),
        position_amount=args.position_amount,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
