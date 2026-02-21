# Strategies AI Guide

## Scope
- Work only inside `strategies/`.
- Responsibility: convert published EPS model outputs into trade candidates, then optimize strategy parameters.
- Do not retrain EPS models here.

## Fixed Convention
- All scripts use `market/year/month`.
- Paths are auto-derived from those three fields.
- Avoid adding manual path/date arguments unless user explicitly requests.

## Pipeline
1. `predict_published.py`
   - Args: `--market --year --month`
   - Reads:
     - `models_eps/<market>/<year>/<month>/latest.json`
     - `train_eps/<market>/<year>/<month>/dataset_evaluate.csv`
   - Writes:
     - `strategies/<market>/<year>/<month>/predictions_published.csv`

2. `build_candidates.py`
   - Args: `--market --year --month`
   - Reads:
     - `strategies/<market>/<year>/<month>/predictions_published.csv`
     - `train_eps/<market>/<year>/<month>/dataset_evaluate.csv`
   - Writes:
     - `strategies/<market>/<year>/<month>/trade_candidates.csv`

3. `cache_daily_quotes.py`
   - Args: `--market --year --month`
   - Auto date window:
     - start: first day of month
     - end: last day of month
   - Reads:
     - `strategies/<market>/<year>/<month>/trade_candidates.csv`
   - Writes:
     - `strategies/<market>/<year>/<month>/daily_quotes_<yyyymm01>_<yyyymmdd>_<market>.csv`

4. `optimize_strategy.py`
   - Args: `--market --year --month`
   - Reads:
     - `strategies/<market>/<year>/<month>/trade_candidates.csv`
     - `strategies/<market>/<year>/<month>/daily_quotes_<yyyymm01>_<yyyymmdd>_<market>.csv`
   - Writes:
     - `strategies/<market>/<year>/<month>/best_strategy.json`
     - `strategies/<market>/<year>/<month>/optimization_results_all.csv`
     - `strategies/<market>/<year>/<month>/optimization_results_top20.csv`
     - `strategies/<market>/<year>/<month>/optimization_summary.json`

## Typical Commands
```powershell
.\.venv\Scripts\python.exe strategies\predict_published.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\build_candidates.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\cache_daily_quotes.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\optimize_strategy.py --market sii --year 2025 --month 09
```

## Rules
- Keep output filename `trade_candidates.csv` fixed.
- Keep directory layout `strategies/<market>/<year>/<month>/`.
- If changing filtering thresholds, update docs and report expected impact.
- Do not commit generated csv/json unless explicitly requested.
