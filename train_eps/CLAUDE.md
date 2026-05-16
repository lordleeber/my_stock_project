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

### Playbook Source of Truth

「月份 → 目標季度」映射的單一 source of truth 在 `train_eps/shared_config.py`：

- `MONTH_TO_TARGET_QNUM`：`{"01": 4, "02": 1, ..., "12": 4}` 純資料表
- `target_quarter_for_playbook(execution_year, month) → (target_year, qnum)`：含 January 推前一年的邏輯
- `shift_quarter(year, qnum, delta)` / `format_quarter(year, qnum)`：跨年季度位移與字串格式化

`step1_prepare_data.build_quarter_context` 與 `step4_predict_and_publish` 都從這裡 import，**改 playbook 只需動 `MONTH_TO_TARGET_QNUM`**。不要在其他檔案複製月份映射表。

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

### `predictions_results.csv` columns
| Column | Meaning |
|---|---|
| `year`, `symbol`, `name`, `industry` | Per-row context |
| `y_true` | Actual target EPS for that target_year/target_quarter (NaN for live future predictions) |
| `pred_lgb_delta` | Model-predicted EPS delta |
| `target_quarter` | The quarter being predicted, e.g. `"2025Q2"` (computed from `year` + playbook `month`) |
| `anchor_quarter` | The quarter whose financials drove the features, e.g. `"2025Q1"` (the row's `anchor_eps`/`xbrl_*_q` came from here) |
| `trained_at_month` | Path-level identifier, e.g. `"2026/05"` — when this prediction run happened |
| `model_pkl` | Exact pkl filename used, e.g. `"20260516080152_0.448.pkl"` (the lowest-MAE pkl in the month dir) |

Looking at the csv alone tells you everything: which quarter was predicted, which quarter's data fed the features, when training happened, and which model checkpoint produced the numbers. Legacy column `fold` (which was just `"year_" + str(year)`) was removed.

## ⚠️ `dataset_train.csv` vs `dataset_evaluate.csv` Naming

Both files contain the **same rows** (every (year, symbol) combination with a valid label). The difference is column set:

| File | Columns |
|---|---|
| `dataset_train.csv` | `year`, `anchor_quarter`, features, `target_eps`, `delta_eps` (minimal — what `train.py` reads) |
| `dataset_evaluate.csv` | + `symbol`, `name`, `industry` (with context — what `evaluate.py`/`predict_and_publish.py` read) |

The names suggest a train/test row split, but it is **not** that. Walk-forward fold splits are done inside `evaluate.py` based on `year`. Treat the names as "lean dataset for training" vs "dataset with row context for evaluation/publishing".

## `anchor_quarter` Column

Both datasets carry an `anchor_quarter` string column (e.g., `"2025Q1"` for a May-playbook row with `year=2025`). The mapping is:

| Playbook month | `anchor_quarter` formula |
|---|---|
| 02-04 | `f"{year-1}Q4"` |
| 05-07 | `f"{year}Q1"` |
| 08-10 | `f"{year}Q2"` |
| 11-12, 01 | `f"{year}Q3"` |

This column is **metadata only** — all three downstream scripts list `anchor_quarter` in their `EXCLUDE_COLUMNS` set so LGBM never sees it as a feature. Its job is to make `anchor_eps`/`xbrl_*_q` self-explanatory without needing to know the playbook month context.

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
