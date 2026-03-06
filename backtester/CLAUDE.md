# Backtester

Walk-forward backtest runner that uses:
- monthly strategy outputs from `strategies/output/<year>/<month>/`
- real historical quotes from DB (`daily_quotes`)

## Required monthly inputs
For each month:
- `strategies/output/<year>/<month>/results_candidates/trade_candidates_<release_yyyymmdd>.csv`
- `strategies/output/<year>/<month>/results_optimize/best_strategy.json`

## Run
Single month (`run.py`):
```bash
venv/bin/python backtester/run.py --year 2023 --month 8
```
Optional position sizing (budget per stock):
```bash
venv/bin/python backtester/run.py --year 2023 --month 8 --position-amount 100000
```

Batch month range (`batch_run.py`) — runs month by month, missing inputs are skipped without interrupting:
```bash
venv/bin/python backtester/batch_run.py --start_year 2023 --start_month 1 --end_year 2023 --end_month 12
```

Baseline single month (`run_baseline.py`):
```bash
venv/bin/python backtester/run_baseline.py --year 2025 --month 10 --position-amount 100000
```

Baseline batch month range (`batch_run_baseline.py`):
```bash
venv/bin/python backtester/batch_run_baseline.py --start_year 2023 --start_month 1 --end_year 2023 --end_month 12 --position-amount 100000
```

## Outputs
Single-month outputs are written to `backtester/output/<year>/<month>/`:
- `trades.csv`
- `monthly_summary.csv`
- `equity_curve.csv`
- `summary.json`

Baseline outputs for the same month:
- `trades_baseline.csv`
- `monthly_summary_baseline.csv`
- `equity_curve_baseline.csv`
- `summary_baseline.json`
  - `summary_baseline.json.strategy_name` = `baseline_target_minus_10pct_buy`

## Baseline Strategy (`*_baseline`)
- Purpose:
  - A simple benchmark to compare against optimized `best_strategy`.
- Entry:
  - Start checking from each stock's `signal_entry_date` (from candidates `entry_date`).
  - Buy when intraday price reaches `predict_target_price * 0.9` or lower.
  - If entry-day open is already below trigger, use open as entry price; otherwise use trigger price.
- Stop loss:
  - After entry, stop out when price falls to `entry_price * 0.9` or below.
- Take profit:
  - Sell when price reaches `predict_target_price`.
- Final exit:
  - If neither stop-loss nor take-profit is hit, sell at the last trading day's close in the month quotes cache file.
  - Example: `daily_quotes_20251001_20251130.csv` -> use last available trading day in that file.
- Position sizing:
  - Budget-based per stock via `--position-amount` (default `100000`), not fixed one-lot.

## Look-ahead safety
- Uses only current month inputs (`trade_candidates` + `best_strategy`) for that month.
- Validates `actual_entry_date >= signal_entry_date`.
- Any look-ahead violation triggers failure and is recorded in `summary.json`.

## Notes
- PnL in backtester is **net** of costs (commission/tax/slippage config).
- Position sizing is budget-based per stock (`--position-amount`, default `100000`), not fixed one-lot.
- `trade_candidates` uses release-date suffix naming under `results_candidates/` (no old path fallback).
