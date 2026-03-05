# train_eps AI Guide

## Scope
- Work only inside `train_eps/`.
- Responsibility: data preparation, training, evaluation, and gated publish.

## Layout
- Month output folders:
  - `train_eps/output/<year>/<month>`
- Shared scripts:
  - `prepare_data.py`
  - `train.py`
  - `evaluate.py`
  - `gate_and_publish.py`
  - `run_pipeline.py`

## Per-Month Data Files
- Required for `train/evaluate/gate`:
  - `dataset_train.csv`
  - `dataset_evaluate.csv`
- Optional month-specific artifacts (not required by `train/evaluate/gate`):
  - `dataset_meta.csv`
  - `dataset_live.csv`

## Standard Flow
1. Run `prepare_data.py --year <year> --month <month>`
2. Run `train.py --year <year> --month <month>`
3. Run `evaluate.py --year <year> --month <month>`
4. Run `gate_and_publish.py --year <year> --month <month>`

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
  - `results_eval/evaluate_by_fold.json`
- It does not write:
  - `results/predictions.csv`
  - `results/valuation_daily_preview.csv`
  - `results/valuation_quality_report.json`

## Current Gate Rule (Default)
- Metric: `mae`
- Compare model: `lgb_delta` vs baseline `baseline_anchor_eps`
- Pass condition: `primary <= baseline * 0.975`

## Published Artifacts
- Gate-passed models are published to `models_eps/<year>/<month>/`:
  - `<timestamp>_<primary_metric>.pkl`
  - `<timestamp>_<primary_metric>.json`
  - `latest.json`

## Typical Commands
```powershell
# Step-by-step
.\.venv\Scripts\python.exe train_eps\prepare_data.py --year 2025 --month 11 --data-source api
.\.venv\Scripts\python.exe train_eps\train.py --year 2025 --month 11
.\.venv\Scripts\python.exe train_eps\evaluate.py --year 2025 --month 11
.\.venv\Scripts\python.exe train_eps\gate_and_publish.py --year 2025 --month 11

# One command pipeline
.\.venv\Scripts\python.exe train_eps\run_pipeline.py --year 2025 --month 11 --data-source api
```

## Health Metrics
- After running `evaluate.py`, check `results_eval/evaluate_by_fold.json`:
  - Confirm fold count for `lgb_delta` is >= gate `min_folds`.
  - Confirm average `mae` of `lgb_delta` is better than `baseline_anchor_eps`.
  ```python
  import pandas as pd
  df = pd.read_json("results_eval/evaluate_by_fold.json")
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
