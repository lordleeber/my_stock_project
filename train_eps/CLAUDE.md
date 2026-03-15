# train_eps AI Guide

## Scope
- Work only inside `train_eps/`.
- Responsibility: data preparation, training, evaluation, and prediction publish.

## Layout
- Month data folders (datasets only):
  - `train_eps/output/<year>/<month>`
- Month model folders (model artifacts):
  - `models_eps/<year>/<month>`
- Shared scripts:
  - `prepare_data.py`
  - `train.py`
  - `evaluate.py`
  - `predict_and_publish.py`
  - `run_pipeline.py`
  - `batch_evaluate.py`
  - `batch_predict_and_publish.py`

## Per-Month Data Files
- Required for `train/evaluate`:
  - `dataset_train.csv`
  - `dataset_evaluate.csv`

## Standard Flow
1. Run `prepare_data.py --year <year> --month <month>`
2. Run `train.py --year <year> --month <month>`
3. Run `evaluate.py --year <year> --month <month>`
4. Run `predict_and_publish.py --year <year> --month <month>`

## One-Command Flow
- Use `run_pipeline.py` to execute all 4 steps in order.
- If any step fails, pipeline stops immediately and writes error details to repo root `error_train_eps.log`.

## Data Source
- `prepare_data.py` defaults to DB mode (`--data-source db`).
- API mode is available with `--data-source api`.

## Monthly Training Calendar
- 01/10 (announce previous Dec revenue): train previous year `Q4 eps delta`.
- 02/10 (announce Jan revenue): train current year `Q1 eps delta`.
- 03/10 (announce Feb revenue): train current year `Q1 eps delta`.
- 04/10 (announce Mar revenue + previous annual report): train current year `Q1 eps delta`.
- 05/15 (announce Apr revenue + Q1 report): train current year `Q2 eps delta`.
- 06/10 (announce May revenue): train current year `Q2 eps delta`.
- 07/10 (announce Jun revenue): train current year `Q2 eps delta`.
- 08/15 (announce Jul revenue + Q2 report): train current year `Q3 eps delta`.
- 09/10 (announce Aug revenue): train current year `Q3 eps delta`.
- 10/10 (announce Sep revenue): train current year `Q3 eps delta`.
- 11/15 (announce Oct revenue + Q3 report): train current year `Q4 eps delta`.
- 12/10 (announce Nov revenue): train current year `Q4 eps delta`.

## Evaluate Output Contract
- `evaluate.py` writes only:
  - `models_eps/<year>/<month>/evaluate_by_fold.json`
- It does not write predictions or model files.

## Model Artifacts
All artifacts written to `models_eps/<year>/<month>/`:
- `{timestamp}_{train_mae:.3f}.pkl` — model file named by training timestamp and in-sample MAE (e.g. `20260301170934_0.705.pkl`). Multiple pkl files may exist per month; `predict_and_publish.py` automatically picks the one with the lowest MAE.
- `train_metrics.json`
- `feature_importance.json`
- `evaluate_by_fold.json` — walk-forward evaluation metrics per fold
- `predictions_results.csv` — EPS delta predictions for the latest year (consumed by `strategies/finalize_strategy.py`)

## Model Naming Convention
- `train.py` saves the model as `{timestamp}_{train_mae:.3f}.pkl` directly to `models_eps/<year>/<month>/`.
- The metric in the filename is the **in-sample train MAE** (`train_mae_lgb_pred_eps`), lower is better.
- `predict_and_publish.py` and `batch_predict_and_publish.py` resolve the model by scanning for `\d{14}_\d+\.\d+\.pkl` and picking the file with the lowest MAE value.
- Do **not** create or expect a `model.pkl` file; that naming was a bug introduced during refactoring.

## Typical Commands
```bash
# Step-by-step
venv/bin/python3 train_eps/prepare_data.py --year 2025 --month 11 --data-source api
venv/bin/python3 train_eps/train.py --year 2025 --month 11
venv/bin/python3 train_eps/evaluate.py --year 2025 --month 11
venv/bin/python3 train_eps/predict_and_publish.py --year 2025 --month 11

# One command pipeline
venv/bin/python3 train_eps/run_pipeline.py --year 2025 --month 11 --data-source api

# Batch historical
venv/bin/python3 train_eps/batch_evaluate.py
venv/bin/python3 train_eps/batch_predict_and_publish.py
```

## Health Metrics
- After running `evaluate.py`, check `models_eps/<year>/<month>/evaluate_by_fold.json`:
  - Confirm fold count for `lgb_delta` is >= gate `min_folds`.
  - Confirm average `mae` of `lgb_delta` is better than `baseline_anchor_eps`.
  ```python
  import pandas as pd
  df = pd.read_json("models_eps/2025/11/evaluate_by_fold.json")
  x = df[df["model"].isin(["lgb_delta", "baseline_anchor_eps"])]
  print(x.groupby("model")["mae"].mean())
  print("folds:", x["fold"].nunique())
  ```

## Prepare Notes
- `train_eps/prepare_data.py` outputs only `dataset_train.csv` and `dataset_evaluate.csv` into `train_eps/output/<year>/<month>/`.
- No `dataset_meta.csv` or `dataset_live.csv` output.
- No `daily_quotes` / `pe_ratio` fetch path.
- Default `--start-year` is `2020` (same as global fetch range).
- For 2020 rows, features that depend on 2019 historical quarters may be missing (`NaN`), including previous-Q4-related fields.
- Missing feature values are allowed in training (LightGBM handles `NaN` natively).
- For both DB and API paths, anchor-quarter samples must have `income_statement + balance_sheet + cash_flow`; otherwise rows are excluded.
- Monthly revenue is handled with full-market scope (`sii + otc`) in pipeline output.
- XBRL features are included for 11-month model:
  - `xbrl_gross_margin_q`, `xbrl_op_margin_q`, `xbrl_rd_ratio_q`, `xbrl_tax_rate_q`
  - `xbrl_current_ratio`, `xbrl_cash_to_assets`, `xbrl_cfo_to_ni_q`, `xbrl_capex_to_revenue_q`
- `cash_flow_xbrl` uses accumulated statements and is converted to single-quarter:
  - `Q3 single-quarter = Q3 accumulated - Q2 accumulated`
- In quantile feature flow, missing values are preserved (no fill to `0`/`0.5`) and remain `NaN` for model-side handling.
- `APPLY_TRADING_FILTER` flag has been removed (no trading-filter switch in current prepare pipeline).
- API mode can be slow; prefer DB mode if available.

## Rules
- Keep feature definitions consistent across `prepare_data.py`, `train.py`, `evaluate.py`.
- Do not commit model binaries and generated csv/json unless explicitly requested.
