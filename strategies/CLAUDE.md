# Strategies AI Guide

## Scope
- Work only inside `strategies/`.
- Responsibility: use published EPS model output to build live candidates and optimize execution rules.
- Do not retrain EPS models in this folder.

## Conventions
- No `market` split in strategy workflow.
- Base output path is fixed: `strategies/output/<year>/<month>/`.
- Keep file names stable unless explicitly requested.
- `02` and `03` are non-training months for this EPS flow.

## Monthly schedule and entry date
- Model release is fixed by month:
  - `05`, `08`, `11`: release after close on day 15, earliest entry day 16.
  - other active months: release after close on day 10, earliest entry day 11.
- `build_candidates.py` sets one month-level `entry_date` by this rule.

## Workflow (current)
### 1) `prepare_data.py`
- Read from DB and build:
  - `dataset_model_input.csv` (model features for prediction)
  - `dataset_strategy.csv` (fields needed by candidate builder)

### 2) `predict_published.py`
- Read model pointer: `models_eps/<year>/<month>/latest.json`.
- Input: `dataset_model_input.csv`.
- Output: `predictions_published.csv` with `pred_lgb_delta`.
- `pred_rf_delta` compatibility fallback is removed.

### 3) `build_candidates.py`
- Build forward EPS/price and apply v1 filters.
- Internal market feature sources (from DB):
  - `technical_indicators`: `ma60`.
  - `daily_quotes`: compute `atr20_pct`.
  - `institutional_investors`: compute `foreign_net_20d_lots`, `inst_net_20d_lots`.
- Derived internal fields:
  - `close_vs_ma60 = q3_close / ma60 - 1`.
  - `atr20_pct = atr20 / close * 100` (`atr20` is 20-day mean of true range).
  - `entry_score = pred_upside_z + chip_score_z + tech_score_z - vol_penalty_z`.
- Hard filters (cumulative):
  - market feature fields must be present (missing -> drop).
  - `volume_lots >= --min-volume-lots` (default `200`).
  - `ttm_eps_forward_live >= ttm_eps_official_live`.
  - `close > ma60`.
  - `foreign_net_20d_lots > 0`.
  - `inst_net_20d_lots > 0`.
  - `atr20_pct <= --max-atr20-pct` (default `6.0`).
- Optional ranking cut:
  - `--top-entry-score-pct` in `(0,1]`, default `1.0` means keep all filtered rows.
- Output remains minimal:
  - `trade_candidates.csv` with `symbol,predict_target_price,close,entry_date`.

### 4) `cache_daily_quotes.py`
- Fetch from DB for 3 periods:
  - current month,
  - last-year same month,
  - last month.
- No `--skip-historical` mode.
- Output:
  - `daily_quotes_<start>_<end>.csv`, where `end = month_end + 30 calendar days`.

### 5) `optimize_strategy.py`
- Historical training periods are mandatory:
  - last-year same month and last month must both exist.
  - missing either period -> error and stop.
- Uses per-stock `entry_date`, then snaps to next trading day.
- Rule-space updates:
  - `entry_rule=all` is disabled.
  - sampled entry rules are gated (`target_above_entry_ratio` or `pullback_from_ref_close`).
- Risk constraints:
  - `--min-entered-count` (default `1`).
  - `--max-stop-loss-ratio` (default `0.5`).
  - trial result includes `stop_loss_count`, `stop_loss_ratio`.
  - score penalizes configs that exceed stop-loss-ratio threshold.
- Outputs:
  - `results_optimize/optimization_results_all.csv`
  - `results_optimize/optimization_results_top20.csv`
  - `results_optimize/best_strategy.json`
  - `results_optimize/current_month_backtest.csv`
  - `results_optimize/optimization_summary.json`

## Batch scripts
- `batch_prepare_data.py`
- `batch_predict_published.py`
- `batch_build_candidates.py`
- `batch_cache_daily_quotes.py`
- `batch_optimize_strategy.py`

## Pipeline
- `run_strategy_pipeline.py` runs:
  - `prepare_data -> predict_published -> build_candidates -> cache_daily_quotes -> optimize_strategy`
- Required args: `--year --month`.
- Optional pass-through: `--n-trials`.
- Abort on first error and write `error_strategies.log`.

## Diagnostics checklist
- If a month performs poorly, check in order:
  - candidate coverage drop (`build_candidates` filter stats),
  - `optimization_results_top20.csv` risk metrics (`stop_loss_ratio`, `entered_count`),
  - `best_strategy.json` entry rule strictness,
  - backtester `trades.csv` exit reason distribution.
- For range comparison, keep before/after snapshots under:
  - `backtester/output/diagnostics/<start>_<end>/`.

## Commands
```bash
venv/bin/python strategies/prepare_data.py --year 2025 --month 09
venv/bin/python strategies/predict_published.py --year 2025 --month 09
venv/bin/python strategies/build_candidates.py --year 2025 --month 09 --min-volume-lots 200 --max-atr20-pct 6.0
venv/bin/python strategies/cache_daily_quotes.py --year 2025 --month 09
venv/bin/python strategies/optimize_strategy.py --year 2025 --month 09 --n-trials 120 --min-entered-count 20 --max-stop-loss-ratio 0.5
```

## Notes
- `revenue_publish_date` is removed.
- Deprecated old strategies (`strategyA~I`, `strategy_fusion`) are out of active flow.
- Avoid look-ahead bias: do not replace historical training periods with current-month data.
