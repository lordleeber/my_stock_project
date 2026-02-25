# Strategies AI Guide

## Scope
- Work only inside `strategies/`.
- Responsibility: convert published EPS model outputs into trade candidates, then optimize strategy parameters.
- Do not retrain EPS models here.

## Fixed Convention
- All scripts use `market/year/month`.
- Paths are auto-derived from those three fields (`strategies/<market>/<year>/<month>/`).
- Avoid adding manual path/date arguments unless user explicitly requests.

## Workflow & Automation (Recommended)
You can run the entire 4-step pipeline using the automation script:
```powershell
.\.venv\Scripts\python.exe strategies\run_strategy_pipeline.py --market sii --year 2025 --month 09
```
- **Aborts on error**: Stops immediately if any step fails.
- **Error Log**: Detailed errors are appended to `error_strategies.log` in the root directory.
- **Environment**: Automatically uses the current Python executable (supports `.venv` or conda).

## Design Principle: Look-ahead Bias Free

> [!IMPORTANT]
> The pipeline is designed to eliminate look-ahead bias. Strategy parameters are
> **never optimized using current-month data**. The current month is only used for
> applying the best params found from historical data.

**Two-phase flow**:
```
[Historical Training]                  [Current Month Application]
Last-year same month + Last month  →   Current candidates
candidates + quotes                →   Apply best params → current_month_backtest.csv
     ↓
Optimize SL/TP params (300 trials)
```

## Detailed Pipeline Logic

### 1. `predict_published.py` (Inference)
- Fetches the best `.pkl` from `models_eps/` and feeds it features from `dataset_evaluate.csv`.
- Generates the raw EPS delta prediction (`pred_rf_delta`).

### 2. `build_candidates.py` (Selection)
- **Forward TTM Fix**: Recomputes TTM EPS by replacing the oldest quarter with the prediction.
- **Filters**: Minimum Forward TTM (2.0), Minimum Volume (500 lots), and non-deteriorating growth.
- **`revenue_publish_date`**: Queries `/raw/monthly-revenue` API per symbol to get the actual date each company published its monthly revenue. This becomes each stock's earliest possible entry date.
  - Fallback: `{year}-{month}-10` if API returns no data.
  - API note: must query per-symbol (market-wide query returns empty).

### 3. `cache_daily_quotes.py` (Environment)
- Fetches OHLCV for **three time periods**:
  1. **Current month**: `{year}/{month}` with 30-day calendar buffer beyond month-end
  2. **Last-year same month**: `{year-1}/{month}` (historical training set A)
  3. **Last month**: `{year}/{month-1}` (historical training set B)
- Each period uses its own `trade_candidates.csv` for the symbol list.
- Skip historical with `--skip-historical` flag.

### 4. `optimize_strategy.py` (Parameter Optimization)
- **Training set**: Loads last-year same month + last month candidates + quotes.
- **Per-stock entry**: `entry_date = revenue_publish_date` (snapped to next trading day if non-trading day).
- **Exit**: `end_date = entry_date + 20 trading days` (not month-end).
- **Grid Search**: 300 random trials across Strategy Families A, B, C.
- **Output**: Best params applied to current month → `current_month_backtest.csv`.
- Key params: `--min-entered-count 1` (default), `--max-hold-days 20` (default).

## Output Files per `strategies/{market}/{year}/{month}/`

| File | Description |
|------|-------------|
| `predictions_published.csv` | EPS delta predictions from model |
| `trade_candidates.csv` | Filtered candidates with `revenue_publish_date` |
| `daily_quotes_*_{market}.csv` | Cached OHLCV (current + 30-day buffer) |
| `optimization_results_all.csv` | All 300 trial results |
| `optimization_results_top20.csv` | Top 20 trials |
| `best_strategy.json` | Best trial params (trained on historical data) |
| `current_month_backtest.csv` | Per-stock result applying best params to current month |
| `optimization_summary.json` | Metadata incl. `training_periods`, `max_hold_days`, `note` |

## Typical Commands
```powershell
# Automated (recommended)
.\.venv\Scripts\python.exe strategies\run_strategy_pipeline.py --market sii --year 2025 --month 09

# Manual Steps
.\.venv\Scripts\python.exe strategies\predict_published.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\build_candidates.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\cache_daily_quotes.py --market sii --year 2025 --month 09
.\.venv\Scripts\python.exe strategies\optimize_strategy.py --market sii --year 2025 --month 09

# If historical data (e.g. 2024/09) does not exist yet, build it first:
.\.venv\Scripts\python.exe strategies\predict_published.py --market sii --year 2024 --month 09
.\.venv\Scripts\python.exe strategies\build_candidates.py --market sii --year 2024 --month 09
.\.venv\Scripts\python.exe strategies\cache_daily_quotes.py --market sii --year 2024 --month 09 --skip-historical
```

## Rules & Design Principles
- Keep output filename `trade_candidates.csv` fixed.
- Main scripts accept only `market/year/month`.
- Do not commit generated csv/json unless explicitly requested.
- If changing filtering thresholds, update docs and report expected impact.
- EPS model training is handled in `train_eps/`, not here.
- **Never use current-month stock price data to optimize strategy parameters** (look-ahead bias).
