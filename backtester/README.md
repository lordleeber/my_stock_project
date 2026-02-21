# backtester

`backtester` runs event-driven monthly backtests based on strategy outputs.

## Directory Convention
- Use: `backtester/<market>/<year>/<month>/`
- Example: `backtester/sii/2025/09/`

## Workflow
1. Build announcements (buy/watch actions)
```powershell
.\.venv\Scripts\python.exe backtester\build_announcements.py --market sii --year 2025 --month 09
```
Output:
- `backtester/sii/2025/09/announcements.csv`

2. Run monthly backtest
```powershell
.\.venv\Scripts\python.exe backtester\run.py --market sii --year 2025 --month 09
```
Outputs:
- `backtester/sii/2025/09/results/signals.csv`
- `backtester/sii/2025/09/results/trades.csv`
- `backtester/sii/2025/09/results/positions_end.csv`
- `backtester/sii/2025/09/results/summary.json`

## Input Files (auto-derived)
- `build_announcements.py` reads:
  - `strategies/<market>/<year>/<month>/trade_candidates.csv`
  - `strategies/<market>/<year>/<month>/best_strategy.json`
  - `strategies/<market>/<year>/<month>/daily_quotes_<yyyymm01>_<yyyymmdd>_<market>.csv`
- `run.py` reads:
  - `backtester/<market>/<year>/<month>/announcements.csv`
  - `strategies/<market>/<year>/<month>/daily_quotes_<yyyymm01>_<yyyymmdd>_<market>.csv`

## Notes
- Execution timing is fixed: signal day, then next trading day open execution.
- No pyramiding is enabled in backtest config by default.
- Generated csv/json files are not committed unless explicitly requested.
