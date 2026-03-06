from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backtester.data_loader import load_candidates, normalize_quotes
from backtester.simulator import CostConfig, aggregate_monthly, build_equity_curve
from backtester.utils import normalize_month, release_yyyymmdd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run baseline backtest for one month.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--tax-rate", type=float, default=0.003)
    parser.add_argument("--slippage-rate", type=float, default=0.0005)
    parser.add_argument("--position-amount", type=float, default=100000.0)
    return parser.parse_args()


def _cost_amount(entry_price: float, exit_price: float, shares: int, cost_cfg: CostConfig) -> float:
    buy = entry_price * shares
    sell = exit_price * shares
    commission = (buy + sell) * cost_cfg.commission_rate
    tax = sell * cost_cfg.tax_rate
    slippage = (buy + sell) * cost_cfg.slippage_rate
    return float(commission + tax + slippage)


def _pick_quotes_cache(base_month_dir: Path) -> Path:
    matches = sorted(glob.glob(str(base_month_dir / "results_quotes_cache" / "daily_quotes_*.csv")))
    if not matches:
        raise FileNotFoundError(f"quotes cache not found in {base_month_dir / 'results_quotes_cache'}")
    return Path(matches[-1])


def _simulate_baseline_one(row: pd.Series, quotes: pd.DataFrame, cost_cfg: CostConfig, position_amount: float) -> dict:
    symbol = str(row["symbol"]).strip()
    signal_entry_date = pd.to_datetime(row["entry_date"])
    target = float(row["predict_target_price"])
    buy_trigger = target * 0.9

    base = {
        "symbol": symbol,
        "strategy_name": "baseline_target_minus_10pct_buy",
        "signal_entry_date": signal_entry_date.strftime("%Y-%m-%d"),
        "target_price": target,
        "entry_reason": "buy_when_price_below_target_10pct",
    }

    q = quotes[(quotes["symbol"] == symbol) & (quotes["date"] >= signal_entry_date)].copy()
    if q.empty:
        return {**base, "status": "no_quote_in_window", "exit_reason": "no_quote_in_window"}
    q = q.sort_values("date").reset_index(drop=True)

    entry_idx = None
    entry_price = None
    actual_entry_date = None

    for i, day in q.iterrows():
        day_open = float(day["open"]) if pd.notna(day["open"]) else np.nan
        day_low = float(day["low"]) if pd.notna(day["low"]) else np.nan
        day_date = pd.to_datetime(day["date"]).strftime("%Y-%m-%d")
        if pd.isna(day_low):
            continue
        if day_low <= buy_trigger:
            if pd.notna(day_open) and day_open <= buy_trigger:
                entry_price = day_open
            else:
                entry_price = buy_trigger
            entry_idx = i
            actual_entry_date = day_date
            break

    if entry_idx is None or entry_price is None or actual_entry_date is None:
        return {
            **base,
            "status": "skipped",
            "actual_entry_date": np.nan,
            "exit_reason": "never_below_target_minus_10pct",
            "entry_price": np.nan,
        }

    shares = max(int(position_amount // entry_price), 1)
    stop_price = entry_price * 0.9
    capital_used = entry_price * shares

    for i in range(entry_idx, len(q)):
        day = q.iloc[i]
        day_high = float(day["high"]) if pd.notna(day["high"]) else np.nan
        day_low = float(day["low"]) if pd.notna(day["low"]) else np.nan
        day_date = pd.to_datetime(day["date"]).strftime("%Y-%m-%d")

        hit_sl = pd.notna(day_low) and day_low <= stop_price
        hit_tp = pd.notna(day_high) and day_high >= target

        if hit_sl and hit_tp:
            exit_price = stop_price
            exit_reason = "both_hit_same_day_stop_first"
        elif hit_sl:
            exit_price = stop_price
            exit_reason = "stop_loss"
        elif hit_tp:
            exit_price = target
            exit_reason = "hit_target_price"
        else:
            continue

        gross_pnl = (exit_price - entry_price) * shares
        total_cost = _cost_amount(entry_price, exit_price, shares, cost_cfg)
        net_pnl = gross_pnl - total_cost
        return_pct = (net_pnl / capital_used * 100.0) if capital_used > 0 else np.nan
        return {
            **base,
            "status": "sold",
            "actual_entry_date": actual_entry_date,
            "exit_reason": exit_reason,
            "exit_date": day_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "shares_bought": shares,
            "capital_used": capital_used,
            "stop_price": stop_price,
            "take_profit_price": target,
            "gross_pnl": gross_pnl,
            "total_cost": total_cost,
            "net_pnl": net_pnl,
            "return_pct": return_pct,
        }

    last = q.iloc[-1]
    last_close = float(last["close"]) if pd.notna(last["close"]) else np.nan
    last_date = pd.to_datetime(last["date"]).strftime("%Y-%m-%d")
    gross_pnl = (last_close - entry_price) * shares if pd.notna(last_close) else np.nan
    total_cost = _cost_amount(entry_price, last_close, shares, cost_cfg) if pd.notna(last_close) else np.nan
    net_pnl = gross_pnl - total_cost if pd.notna(gross_pnl) else np.nan
    return_pct = (net_pnl / capital_used * 100.0) if capital_used > 0 and pd.notna(net_pnl) else np.nan
    return {
        **base,
        "status": "open_until_end",
        "actual_entry_date": actual_entry_date,
        "exit_reason": "sell_on_last_day",
        "exit_date": last_date,
        "entry_price": entry_price,
        "exit_price": last_close,
        "shares_bought": shares,
        "capital_used": capital_used,
        "stop_price": stop_price,
        "take_profit_price": target,
        "gross_pnl": gross_pnl,
        "total_cost": total_cost,
        "net_pnl": net_pnl,
        "return_pct": return_pct,
    }


def run_month_baseline(year: int, month: int, cost_cfg: CostConfig, position_amount: float = 100000.0) -> dict:
    month_s = normalize_month(month)
    strategies_month_dir = (Path.cwd() / "strategies" / "output" / f"{year:04d}" / month_s).resolve()
    candidates_path = (
        strategies_month_dir / "results_candidates" / f"trade_candidates_{release_yyyymmdd(year, month)}.csv"
    )
    quotes_cache_path = _pick_quotes_cache(strategies_month_dir)
    out_dir = (Path.cwd() / "backtester" / "output" / f"{year:04d}" / month_s).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_candidates(candidates_path)
    quotes = normalize_quotes(pd.read_csv(quotes_cache_path))

    rows = [_simulate_baseline_one(row, quotes, cost_cfg, position_amount) for _, row in candidates.iterrows()]
    trades = pd.DataFrame(rows)
    num_cols = trades.select_dtypes(include=["number"]).columns.tolist()
    if num_cols:
        trades[num_cols] = trades[num_cols].round(6)

    trades_path = out_dir / "trades_baseline.csv"
    monthly_path = out_dir / "monthly_summary_baseline.csv"
    equity_path = out_dir / "equity_curve_baseline.csv"
    summary_path = out_dir / "summary_baseline.json"

    trades.to_csv(trades_path, index=False, encoding="utf-8-sig")
    monthly = aggregate_monthly(trades)
    monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    equity = build_equity_curve(trades)
    equity.to_csv(equity_path, index=False, encoding="utf-8-sig")

    summary = {
        "year": year,
        "month": month_s,
        "strategy_name": "baseline_target_minus_10pct_buy",
        "buy_rule": "buy when price <= target_price * 0.9 after signal entry date",
        "stop_loss_rule": "sell when price <= entry_price * 0.9",
        "take_profit_rule": "sell when price >= target_price",
        "final_exit_rule": "if neither stop nor target hit, sell at last trading day close in quotes cache",
        "candidates_path": str(candidates_path),
        "quotes_cache_path": str(quotes_cache_path),
        "cost_config": {
            "commission_rate": cost_cfg.commission_rate,
            "tax_rate": cost_cfg.tax_rate,
            "slippage_rate": cost_cfg.slippage_rate,
        },
        "position_amount": position_amount,
        "rows": int(len(trades)),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "output_dir": str(out_dir),
        "trades_baseline": str(trades_path),
        "monthly_summary_baseline": str(monthly_path),
        "equity_curve_baseline": str(equity_path),
        "summary_baseline": str(summary_path),
    }


def main() -> None:
    args = parse_args()
    year = int(args.year)
    month = int(args.month)
    cost_cfg = CostConfig(
        commission_rate=args.commission_rate,
        tax_rate=args.tax_rate,
        slippage_rate=args.slippage_rate,
    )
    result = run_month_baseline(year=year, month=month, cost_cfg=cost_cfg, position_amount=args.position_amount)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
