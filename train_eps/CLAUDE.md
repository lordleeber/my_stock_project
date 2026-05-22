# train_eps AI Guide

## Scope
- Work only inside `train_eps/`.
- Responsibility: data preparation, training, evaluation, and prediction publish.

## Layout
- Per-playbook data folders (datasets only):
  - `train_eps/output/<YYYY-MM-DD>/`
- Per-playbook model folders (model artifacts):
  - `models_eps/<YYYY-MM-DD>/`
- Shared scripts:
  - `step1_prepare_data.py`
  - `step2_train.py`
  - `step3_evaluate.py`
  - `step4_predict_and_publish.py`
  - `run_pipeline.py`
  - `step3_batch_evaluate.py`
  - `step4_batch_predict_and_publish.py`
  - `step5_backfill_eps_predictions.py`

> `<YYYY-MM-DD>` 必須是 canonical playbook run date：**訓練實際執行日 = cutoff（公告日）+ 1 天**。5/8/11 月為 16 號，其餘月份為 11 號。由 `shared_config.playbook_run_date(year, month)` 唯一決定；off-cycle 日期會被 `parse_playbook_date` 直接拒絕。
>
> 跟 strategies 的 `cutoff_date` 概念差一天：strategies 用公告日做 PIT 資料截斷，train_eps 用公告日 +1 作為實際跑訓練那天的目錄名。

## Per-Playbook Data Files
- Required for `step2/step3`:
  - `dataset_train.csv`
  - `dataset_evaluate.csv`

## Standard Flow
所有 step 一律吃 `--date YYYY-MM-DD`（無 `--year` / `--month`），且 `--date` 必須是 cutoff +1：

1. `step1_prepare_data.py --date 2025-10-11`
2. `step2_train.py             --date 2025-10-11`
3. `step3_evaluate.py          --date 2025-10-11`
4. `step4_predict_and_publish.py --date 2025-10-11`

### `--date` 自動 fallback
step1~4 與 `run_pipeline.py` 的 `--date` 都是 optional。省略時自動鎖到 `latest_playbook_date()`：今天當下最新的 canonical 日（≤ today 的最大值）。

- 今天 2026-05-20 → 自動用 2026-05-16
- 今天 2026-05-16 → 用 2026-05-16
- 今天 2026-05-15 → 5 月還沒到 canonical，退回 2026-04-11
- 今天 2026-01-05 → 跨年回到 2025-12-11

實際 fire 時會印 `[auto] --date 未指定，使用最新 canonical playbook date: <date>`。腳本化排程（不靠 `--date`）跑「最新一輪」適用這個 default；明確要重跑某個歷史月仍應顯式傳 `--date`。

## One-Command Flow
- Use `run_pipeline.py` to execute all 4 steps in order.
- If any step fails, pipeline stops immediately and writes error details to repo root `error_train_eps.log`.

## Data Source
- `prepare_data.py` reads PostgreSQL directly (XBRL tables only). API mode has been removed — there is no `--data-source` flag.

## Playbook Run Date Calendar
每月一次 canonical 訓練執行日（= cutoff 公告日 +1）。5/8/11 月為 16 號（季報公告日 +1），其餘月份為 11 號（月營收公告日 +1）：

| `--date` (執行日) | cutoff (公告日) | 公告事件 | 預測目標 |
|---|---|---|---|
| `YYYY-01-11` | `YYYY-01-10` | 前一年 12 月營收 | 前一年 `Q4 eps delta` |
| `YYYY-02-11` | `YYYY-02-10` | 1 月營收 | 當年 `Q1 eps delta` |
| `YYYY-03-11` | `YYYY-03-10` | 2 月營收 | 當年 `Q1 eps delta` |
| `YYYY-04-11` | `YYYY-04-10` | 3 月營收 + 前一年年報 | 當年 `Q1 eps delta` |
| `YYYY-05-16` | `YYYY-05-15` | 4 月營收 + Q1 報 | 當年 `Q2 eps delta` |
| `YYYY-06-11` | `YYYY-06-10` | 5 月營收 | 當年 `Q2 eps delta` |
| `YYYY-07-11` | `YYYY-07-10` | 6 月營收 | 當年 `Q2 eps delta` |
| `YYYY-08-16` | `YYYY-08-15` | 7 月營收 + Q2 報 | 當年 `Q3 eps delta` |
| `YYYY-09-11` | `YYYY-09-10` | 8 月營收 | 當年 `Q3 eps delta` |
| `YYYY-10-11` | `YYYY-10-10` | 9 月營收 | 當年 `Q3 eps delta` |
| `YYYY-11-16` | `YYYY-11-15` | 10 月營收 + Q3 報 | 當年 `Q4 eps delta` |
| `YYYY-12-11` | `YYYY-12-10` | 11 月營收 | 當年 `Q4 eps delta` |

### Playbook Source of Truth

`train_eps/shared_config.py` 唯一定義整個 playbook：

- `MONTH_TO_TARGET_QNUM`：`{"01": 4, "02": 1, ..., "12": 4}` 純資料表
- `target_quarter_for_playbook(execution_year, month) → (target_year, qnum)`：含 January 推前一年的邏輯
- `playbook_run_date(year, month) → "YYYY-MM-DD"`：cutoff +1（5/8/11 月 = 16 號；其他月份 = 11 號）
- `parse_playbook_date("YYYY-MM-DD") → (year, month_str)`：嚴格驗證該日是 canonical playbook run date，off-cycle 直接報錯（例如誤傳 cutoff 公告日如 2026-05-15 會被拒絕，提示應為 2026-05-16）
- `shift_quarter(year, qnum, delta)` / `format_quarter(year, qnum)`：跨年季度位移與字串格式化

所有 step1~4 / batch / run_pipeline 都從這裡 import，**改 playbook 只需動 `MONTH_TO_TARGET_QNUM` 與 `playbook_run_date` 的 day 公式**。不要在其他檔案複製月份映射表或日期公式。strategies 構建 `models_eps/<YYYY-MM-DD>/` 路徑時也 import 同一支 helper。

## Evaluate Output Contract
- `step3_evaluate.py` writes only:
  - `models_eps/<YYYY-MM-DD>/evaluate_by_fold.json`
- It does not write predictions or model files.

## Model Artifacts
All artifacts written to `models_eps/<YYYY-MM-DD>/`:
- `{timestamp}_{train_mae:.3f}.pkl` — model file named by training timestamp and in-sample MAE (e.g. `20260301170934_0.705.pkl`). Multiple pkl files may exist per playbook date; `step4_predict_and_publish.py` automatically picks the one with the lowest MAE.
- `train_metrics.json`
- `feature_importance.json`
- `evaluate_by_fold.json` — walk-forward evaluation metrics per fold
- `predictions_results.csv` — EPS delta predictions for the latest year (consumed by `strategies/step2_finalize_strategy.py`)

### `predictions_results.csv` columns
| Column | Meaning |
|---|---|
| `year`, `symbol`, `name`, `industry` | Per-row context |
| `y_true` | Actual target EPS for that target_year/target_quarter (NaN for live future predictions) |
| `anchor_eps` | Per-row anchor-quarter EPS (the row's `dataset_evaluate.csv["anchor_eps"]`) |
| `pred_lgb_delta` | Model-predicted EPS delta |
| `predict_eps` | Absolute predicted EPS = `anchor_eps + pred_lgb_delta`. This is what `calculator/calculate_valuation.py` reads from `eps_predictions`. |
| `target_quarter` | The quarter being predicted, e.g. `"2025Q2"` (computed from playbook `--date` via `target_quarter_for_playbook`) |
| `anchor_quarter` | The quarter whose financials drove the features, e.g. `"2025Q1"` (the row's `anchor_eps`/`xbrl_*_q` came from here) |
| `playbook_date` | This run's `--date`, e.g. `"2026-05-15"` (canonical playbook run date) |
| `trained_at_date` | Day-precision training date (`YYYY-MM-DD`) parsed from `model_pkl` timestamp; the day the pkl was actually saved (may differ from `playbook_date` when re-running an old playbook); used as `model_version` in the DB |
| `model_pkl` | Exact pkl filename used, e.g. `"20260516080152_0.448.pkl"` (the lowest-MAE pkl in the date dir) |

Looking at the csv alone tells you everything: which quarter was predicted, which quarter's data fed the features, when the playbook ran, when training actually happened, and which model checkpoint produced the numbers. Legacy columns `fold` (= `"year_" + str(year)`) and `trained_at_month` (= `"YYYY/MM"`) were removed.

### DB Publish (step4 only)
`step4_predict_and_publish.py` additionally upserts results into PostgreSQL table `eps_predictions` after writing the CSV:

| Column | Source |
|---|---|
| `target_quarter` | from this playbook run |
| `symbol` | row symbol |
| `predict_eps` | `anchor_eps + pred_lgb_delta` |
| `model_version` | `trained_at_date` (e.g. `"2026-05-16"`) |
| `created_at` | timestamp of the DB write |

Write strategy: `DELETE WHERE target_quarter = '<this run>'` followed by bulk INSERT. Different playbook dates publishing the same target_quarter (e.g. 2026-05-15 / 2026-06-10 / 2026-07-10 all → 2026Q2) overwrite each other — the latest run wins.

`calculator/calculate_valuation.py` reads this table to compute forward TTM / forward PE / target price / forward ROE. If the table is empty, all forward metrics collapse to backward equivalents (fail-silent fallback inside calculate_valuation.py — by design).

### Historical backfill
`train_eps/step5_backfill_eps_predictions.py` is a one-off utility that walks every `models_eps/<YYYY-MM-DD>/predictions_results.csv`, dedups on `(symbol, target_quarter)` by latest `playbook_date` (tie-broken by `trained_at_date`), and DROP+CREATE+INSERTs the `eps_predictions` table. For legacy CSVs missing `anchor_eps`/`predict_eps`/`playbook_date`/`trained_at_date`, it joins `quarterly_reports_xbrl.eps_q` on `anchor_quarter` to recover `anchor_eps` and derives the rest (`playbook_date` from the path, `trained_at_date` from the pkl timestamp).

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
- `step2_train.py` saves the model as `{timestamp}_{train_mae:.3f}.pkl` directly to `models_eps/<YYYY-MM-DD>/`.
- The metric in the filename is the **in-sample train MAE** (`train_mae_lgb_pred_eps`), lower is better.
- `step4_predict_and_publish.py` and `step4_batch_predict_and_publish.py` resolve the model by scanning for `\d{14}_\d+\.\d+\.pkl` and picking the file with the lowest MAE value.
- Do **not** create or expect a `model.pkl` file; that naming was a bug introduced during refactoring.

## Typical Commands
```bash
# Step-by-step (canonical playbook date: 11 月 cutoff 是 11/15，執行日 = 11/16)
venv/bin/python3 train_eps/step1_prepare_data.py        --date 2025-11-16
venv/bin/python3 train_eps/step2_train.py               --date 2025-11-16
venv/bin/python3 train_eps/step3_evaluate.py            --date 2025-11-16
venv/bin/python3 train_eps/step4_predict_and_publish.py --date 2025-11-16

# One command pipeline
venv/bin/python3 train_eps/run_pipeline.py --date 2025-11-16

# Batch historical
venv/bin/python3 train_eps/step3_batch_evaluate.py
venv/bin/python3 train_eps/step4_batch_predict_and_publish.py
```

## Health Metrics
- After running `step3_evaluate.py`, check `models_eps/<YYYY-MM-DD>/evaluate_by_fold.json`:
  - Confirm fold count for `lgb_delta` is >= gate `min_folds`.
  - Confirm average `mae` of `lgb_delta` is better than `baseline_anchor_eps`.
  ```python
  import pandas as pd
  df = pd.read_json("models_eps/2025-11-16/evaluate_by_fold.json")
  x = df[df["model"].isin(["lgb_delta", "baseline_anchor_eps"])]
  print(x.groupby("model")["mae"].mean())
  print("folds:", x["fold"].nunique())
  ```

## Prepare Notes
- `train_eps/step1_prepare_data.py` outputs only `dataset_train.csv` and `dataset_evaluate.csv` into `train_eps/output/<YYYY-MM-DD>/`.
- No `dataset_meta.csv` or `dataset_live.csv` output.
- No `daily_quotes` / `pe_ratio` fetch path.
- Default `--start-year` is `2020` (same as global fetch range).
- For 2020 rows, features that depend on 2019 historical quarters may be missing (`NaN`), including previous-Q4-related fields.
- Missing feature values are allowed in training (LightGBM handles `NaN` natively).
- Anchor-quarter samples must have `income_statement_xbrl + balance_sheet_xbrl + cash_flow_xbrl`; otherwise rows are excluded.
- Monthly revenue is handled with full-market scope (`sii + otc`) in pipeline output.
- XBRL features are included for 11-month model:
  - `xbrl_gross_margin_q`, `xbrl_op_margin_q`, `xbrl_rd_ratio_q`, `xbrl_tax_rate_q`
  - `xbrl_current_ratio`, `xbrl_cash_to_assets`, `xbrl_cfo_to_ni_q`, `xbrl_capex_to_revenue_q`
- `cash_flow_xbrl` uses accumulated statements and is converted to single-quarter:
  - `Q3 single-quarter = Q3 accumulated - Q2 accumulated`
- In quantile feature flow, missing values are preserved (no fill to `0`/`0.5`) and remain `NaN` for model-side handling.
- `APPLY_TRADING_FILTER` flag has been removed (no trading-filter switch in current prepare pipeline).

## Rules
- Keep feature definitions consistent across `step1_prepare_data.py`, `step2_train.py`, `step3_evaluate.py`.
- Do not commit model binaries and generated csv/json unless explicitly requested.
