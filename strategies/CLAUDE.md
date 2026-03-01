# Strategies AI Guide

## Scope
- Work only inside `strategies/`.
- Responsibility: use published EPS models to generate candidates, cache quotes, and optimize strategy params.
- Do not retrain EPS models here.

## Fixed Convention
- No `market` split in new workflow.
- Base path: `strategies/output/<year>/<month>/`.
- Keep filenames stable unless explicitly requested.

## Workflow (Current)
### 1. `prepare_data.py`
- Build strategy datasets from DB.
- Outputs:
  - `dataset_model_input.csv`
  - `dataset_strategy.csv`

### 2. `predict_published.py`
- Load `models_eps/<year>/<month>/latest.json` and published model.
- Input: `dataset_model_input.csv`
- Output: `predictions_published.csv` with `pred_lgb_delta`.

### 3. `build_candidates.py`
- Build forward EPS/price fields and filter candidates.
- Current filter:
  - `volume_lots >= 200`
  - `ttm_eps_forward_live >= ttm_eps_official_live`
- Entry timing is fixed by schedule rule (not per-symbol publish date):
  - month in `{05,08,11}` -> entry date = day 16
  - otherwise -> entry date = day 11
- Output: minimal `trade_candidates.csv` columns:
  - `symbol,predict_target_price,close,entry_date`

### 4. `cache_daily_quotes.py`
- Cache quotes from DB for 3 periods:
  - current month
  - last-year same month
  - last month
- No `--skip-historical` mode.
- Output per period:
  - `daily_quotes_<start>_<end>.csv`
  - end date is month-end + 30 calendar days buffer.

### 5. `optimize_strategy.py`
- Historical training set is mandatory and must include both:
  - last-year same month
  - last month
- Missing either period -> raise error and stop.
- Uses per-stock `entry_date`, then snaps to next trading day if needed.
- Outputs to:
  - `strategies/output/<year>/<month>/results_optimize/`
    - `optimization_results_all.csv`
    - `optimization_results_top20.csv`
    - `best_strategy.json`
    - `current_month_backtest.csv`
    - `optimization_summary.json`

## Automation
- `run_strategy_pipeline.py` now runs 5 steps:
  - `prepare_data -> predict_published -> build_candidates -> cache_daily_quotes -> optimize_strategy`
- Args:
  - required: `--year`, `--month`
  - optional: `--n-trials` (pass-through to optimize step)
- Aborts immediately on first error and writes to `error_strategies.log`.

## Commands
```bash
venv/bin/python strategies/run_strategy_pipeline.py --year 2023 --month 08
venv/bin/python strategies/run_strategy_pipeline.py --year 2023 --month 08 --n-trials 5
```

Manual:
```bash
venv/bin/python strategies/prepare_data.py --year 2023 --month 08
venv/bin/python strategies/predict_published.py --year 2023 --month 08
venv/bin/python strategies/build_candidates.py --year 2023 --month 08
venv/bin/python strategies/cache_daily_quotes.py --year 2023 --month 08
venv/bin/python strategies/optimize_strategy.py --year 2023 --month 08
```

## Notes
- `revenue_publish_date` is removed for now.
- `strategyA~I` and `strategy_fusion` are deprecated and removed from active tracking.
- Avoid look-ahead bias: never optimize using current-month data as historical training substitute.
