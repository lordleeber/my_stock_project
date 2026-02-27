# train_eps AI Guide

## Scope
- Work only inside `train_eps/`.
- Responsibility: data preparation, training, evaluation, and gated publish.

## Layout
- Month folders:
  - `train_eps/sii/<year>/<month>`
  - `train_eps/otc/<year>/<month>`
- Shared scripts:
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
1. Run month-specific `prepare_data.py`
2. Run `train.py --market <market> --year <year> --month <month>`
3. Run `evaluate.py --market <market> --year <year> --month <month>`
4. Run `gate_and_publish.py --market <market> --year <year> --month <month>`

## One-Command Flow
- Use `run_pipeline.py` to execute all 4 steps in order.
- If any step fails, pipeline stops immediately and writes error details to repo root `error_train_eps.log`.

## Data Source
- `prepare_data.py` defaults to DB mode (`--data-source db`, usually `DB_HOST=db`).
- API mode is available with `--data-source api`.

## Evaluate Output Contract
- `evaluate.py` writes only:
  - `results/evaluate_by_fold.csv`
- It does not write:
  - `results/predictions.csv`
  - `results/valuation_daily_preview.csv`
  - `results/valuation_quality_report.json`

## Current Gate Rule (Default)
- Metric: `mae`
- Compare model: `lgb_delta` vs baseline `baseline_anchor_eps`
- Pass condition: `primary <= baseline * 0.975`

## Published Artifacts
- Gate-passed models are published to `models_eps/<market>/<year>/<month>/`:
  - `<timestamp>.pkl`
  - `<timestamp>.json`
  - `latest.json`

## Typical Commands
```powershell
# Step-by-step
.\.venv\Scripts\python.exe train_eps\sii\2025\11\prepare_data.py --data-source api --start-year 2022 --end-year 2024
.\.venv\Scripts\python.exe train_eps\train.py --market sii --year 2025 --month 11
.\.venv\Scripts\python.exe train_eps\evaluate.py --market sii --year 2025 --month 11
.\.venv\Scripts\python.exe train_eps\gate_and_publish.py --market sii --year 2025 --month 11

# One command pipeline
.\.venv\Scripts\python.exe train_eps\run_pipeline.py --market sii --year 2025 --month 11 --data-source api
```

## 05/06/07 Specific Rules
- For 05/06/07 prepare scripts:
  - Default `--start-year` is `2021`.
  - Exclude rows where previous Q4 income-statement row does not exist.
  - Exclude rows where previous Q4 `revenue_q` is `NaN` or `0`.
  - After exclusions, if `prev_q4_margin` still has missing values, raise error and stop.

## Health Metrics
- After running `evaluate.py`, check `results/evaluate_by_fold.csv`:
  - Confirm fold count for `lgb_delta` is >= gate `min_folds`.
  - Confirm average `mae` of `lgb_delta` is better than `baseline_anchor_eps`.
  ```python
  import pandas as pd
  df = pd.read_csv("results/evaluate_by_fold.csv")
  x = df[df["model"].isin(["lgb_delta", "baseline_anchor_eps"])]
  print(x.groupby("model")["mae"].mean())
  print("folds:", x["fold"].nunique())
  ```

## 2025/11 Notes
- `train_eps/sii/2025/11/prepare_data.py` is intentionally lean:
  - Outputs only `dataset_train.csv` and `dataset_evaluate.csv`.
  - No `dataset_meta.csv` or `dataset_live.csv` output in this month script.
  - No `daily_quotes` / `pe_ratio` fetch path in this month script.
- XBRL features are included for 11-month model:
  - `xbrl_gross_margin_q`, `xbrl_op_margin_q`, `xbrl_rd_ratio_q`, `xbrl_tax_rate_q`
  - `xbrl_current_ratio`, `xbrl_cash_to_assets`, `xbrl_cfo_to_ni_q`, `xbrl_capex_to_revenue_q`
- `cash_flow_xbrl` uses accumulated statements and is converted to single-quarter:
  - `Q3 single-quarter = Q3 accumulated - Q2 accumulated`
- API mode for 11-month script can be slow; prefer narrowing years with
  - `--start-year` / `--end-year`
  - DB mode if available

## Rules
- Keep feature definitions consistent across `prepare_data.py`, `train.py`, `evaluate.py`.
- Do not commit model binaries and generated csv/json unless explicitly requested.
