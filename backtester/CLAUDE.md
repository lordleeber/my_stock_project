# Backtester

Walk-forward backtest runner that uses:
- monthly strategy outputs from `strategies/output/<year>/<month>/`
- real historical quotes from DB (`daily_quotes`)

## Required monthly inputs
For each month in range:
- `strategies/output/<year>/<month>/trade_candidates.csv`
- `strategies/output/<year>/<month>/results_optimize/best_strategy.json`

## Run
Strict mode (default, missing input -> fail):
```bash
venv/bin/python backtester/run.py --start_year 2023 --start_month 8 --end_year 2023 --end_month 8
```

Allow missing months and mark skipped:
```bash
venv/bin/python backtester/run.py --start_year 2023 --start_month 1 --end_year 2023 --end_month 12 --allow-missing-input
```

## Outputs
Written to `backtester/output/<startYYYYMM>_<endYYYYMM>/`:
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
