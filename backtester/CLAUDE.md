# Backtester

Walk-forward backtest runner that uses:
- monthly strategy outputs from `strategies/output/<year>/<month>/`
- real historical quotes from DB (`daily_quotes`)

## Required monthly inputs
For each month:
- `strategies/output/<year>/<month>/trade_candidates.csv`
- `strategies/output/<year>/<month>/results_optimize/best_strategy.json`

## Run
Single month (`run.py`):
```bash
venv/bin/python backtester/run.py --year 2023 --month 8
```

Batch month range (`batch_run.py`) — runs month by month, missing inputs are skipped without interrupting:
```bash
venv/bin/python backtester/batch_run.py --start_year 2023 --start_month 1 --end_year 2023 --end_month 12
```

## Outputs
Single-month outputs are written to `backtester/output/<year>/<month>/`:
- `trades.csv`
- `monthly_summary.csv`
- `equity_curve.csv`
- `summary.json`

## Look-ahead safety
- Uses only current month inputs (`trade_candidates` + `best_strategy`) for that month.
- Validates `actual_entry_date >= signal_entry_date`.
- Any look-ahead violation triggers failure and is recorded in `summary.json`.

## Notes
- PnL in backtester is **net** of costs (commission/tax/slippage config).
- If comparing to `strategies/.../current_month_backtest.csv`, exit reasons and dates should align; pnl may differ due to cost handling.
