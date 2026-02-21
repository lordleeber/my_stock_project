# Stock Analysis Project

This repository is organized around a monthly EPS-to-strategy-to-backtest workflow.

## Current Core Flow
1. `train_eps/`  
   Build datasets, train EPS model, evaluate, and publish gated model.
2. `strategies/`  
   Convert published predictions into trade candidates, cache daily quotes, optimize strategy params.
3. `backtester/`  
   Build announcement signals from candidates + best strategy, then run monthly backtest.

## Directory Overview
- `train_eps/`: model training pipeline (market/year/month)
- `models_eps/`: published models (market/year/month)
- `strategies/`: candidate + optimization pipeline (market/year/month)
- `backtester/`: announcement builder + backtest runner (market/year/month)
- `backend/`: API service and data endpoints
- `frontend/`: UI
- `common/`: shared schema and utility modules

## Quick Start (SII 2025/09)
1. Prepare and publish model
```powershell
.\.venv\Scripts\python.exe train_eps\sii\2025\09\prepare_data.py --data-source api
.\.venv\Scripts\python.exe train_eps\train.py --month-dir train_eps\sii\2025\09 --n-jobs 1
.\.venv\Scripts\python.exe train_eps\evaluate.py --month-dir train_eps\sii\2025\09 --n-jobs 1
.\.venv\Scripts\python.exe train_eps\gate_and_publish.py --month-dir train_eps\sii\2025\09 --models-root models_eps
```

2. Build strategy artifacts
```powershell
.\.venv\Scripts\python.exe strategies\predict_published.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\build_candidates.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\cache_daily_quotes.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\optimize_strategy.py --market sii --year 2025 --month 09
```

3. Run backtest
```powershell
.\.venv\Scripts\python.exe backtester\build_announcements.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe backtester\run.py --market sii --year 2025 --month 09
```

## Outputs
- Training:
  - `train_eps/<market>/<year>/<month>/...`
  - `models_eps/<market>/<year>/<month>/latest.json`
- Strategy:
  - `strategies/<market>/<year>/<month>/trade_candidates.csv`
  - `strategies/<market>/<year>/<month>/best_strategy.json`
- Backtest:
  - `backtester/<market>/<year>/<month>/announcements.csv`
  - `backtester/<market>/<year>/<month>/results/summary.json`

## Notes
- Main scripts now use `market/year/month` as the primary interface.
- Generated csv/json/pkl artifacts are usually not committed unless explicitly requested.
