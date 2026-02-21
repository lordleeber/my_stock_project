# Backtester AI Guide

## Scope
- Work only inside `backtester/`.
- Do not retrain models here. Training is handled in `train_eps/`.
- Strategy candidate generation is handled in `strategies/`.

## Current Workflow
1. Build announcements from strategy outputs:
   - `backtester/build_announcements.py --market --year --month`
2. Run monthly backtest:
   - `backtester/run.py --market --year --month`

## Fixed Convention
- Scripts use `market/year/month`.
- Paths and monthly date windows are auto-derived from those fields.
- Avoid adding manual path/date arguments unless explicitly requested.

## Inputs
- `build_announcements.py` reads:
  - `strategies/<market>/<year>/<month>/trade_candidates.csv`
  - `strategies/<market>/<year>/<month>/best_strategy.json`
  - `strategies/<market>/<year>/<month>/daily_quotes_<yyyymm01>_<yyyymmdd>_<market>.csv`
- `run.py` reads:
  - `backtester/<market>/<year>/<month>/announcements.csv`
  - `strategies/<market>/<year>/<month>/daily_quotes_<yyyymm01>_<yyyymmdd>_<market>.csv`

## Outputs
- `build_announcements.py` writes:
  - `backtester/<market>/<year>/<month>/announcements.csv`
- `run.py` writes:
  - `backtester/<market>/<year>/<month>/results/signals.csv`
  - `backtester/<market>/<year>/<month>/results/trades.csv`
  - `backtester/<market>/<year>/<month>/results/positions_end.csv`
  - `backtester/<market>/<year>/<month>/results/summary.json`

## Typical Commands
```powershell
.\.venv\Scripts\python.exe backtester\build_announcements.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe backtester\run.py --market sii --year 2025 --month 09
```

## Rules
- Keep signal timing unchanged: signal day -> next trading day open execution.
- Keep no-pyramiding behavior unless explicitly requested.
- Do not commit generated csv/json files unless explicitly requested.
