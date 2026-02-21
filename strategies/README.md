# strategies

`strategies` converts published EPS model outputs into trade candidates and optimizes strategy parameters.

## Directory Convention
- Always use: `strategies/<market>/<year>/<month>/`
- Example: `strategies/sii/2025/09/`

## Workflow
1. Generate predictions from published model
```powershell
.\.venv\Scripts\python.exe strategies\predict_published.py --market sii --year 2025 --month 09
```
Output:
- `strategies/sii/2025/09/predictions_published.csv`

2. Build trade candidates
```powershell
.\.venv\Scripts\python.exe strategies\build_candidates.py --market sii --year 2025 --month 09
```
Output:
- `strategies/sii/2025/09/trade_candidates.csv`

3. Cache daily quotes for that month
```powershell
.\.venv\Scripts\python.exe strategies\cache_daily_quotes.py --market sii --year 2025 --month 09
```
Output:
- `strategies/sii/2025/09/daily_quotes_20250901_20250930_sii.csv`

4. Optimize strategy parameters
```powershell
.\.venv\Scripts\python.exe strategies\optimize_strategy.py --market sii --year 2025 --month 09
```
Outputs:
- `strategies/sii/2025/09/best_strategy.json`
- `strategies/sii/2025/09/optimization_results_all.csv`
- `strategies/sii/2025/09/optimization_results_top20.csv`
- `strategies/sii/2025/09/optimization_summary.json`

## Design Principles
- Main scripts accept only `market/year/month`.
- Paths and date windows are auto-derived from `market/year/month`.
- `trade_candidates.csv` filename is fixed.

## Notes
- EPS model training is handled in `train_eps/`, not here.
- Generated csv/json files are not committed unless explicitly requested.
