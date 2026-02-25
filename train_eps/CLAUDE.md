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
- `dataset_train.csv`
- `dataset_evaluate.csv`
- `dataset_meta.csv`

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

## Current Gate Rule (Default)
- Metric: `mae`
- Compare model: `rf_delta` vs baseline `baseline_anchor_eps`
- Pass condition: `primary <= baseline * 0.975`

## Published Artifacts
- Gate-passed models are published to `models_eps/<market>/<year>/<month>/`:
  - `<timestamp>.pkl`
  - `<timestamp>.json`
  - `latest.json`

## Typical Commands
```powershell
# Step-by-step
.\.venv\Scripts\python.exe train_eps\sii\2025\10\prepare_data.py --data-source api
.\.venv\Scripts\python.exe train_eps\train.py --market sii --year 2025 --month 10
.\.venv\Scripts\python.exe train_eps\evaluate.py --market sii --year 2025 --month 10
.\.venv\Scripts\python.exe train_eps\gate_and_publish.py --market sii --year 2025 --month 10

# One command pipeline
.\.venv\Scripts\python.exe train_eps\run_pipeline.py --market sii --year 2025 --month 10 --data-source api
```

## 05/06/07 Specific Rules
- For 05/06/07 prepare scripts:
  - Default `--start-year` is `2021`.
  - Exclude rows where previous Q4 income-statement row does not exist.
  - Exclude rows where previous Q4 `revenue_q` is `NaN` or `0`.
  - After exclusions, if `prev_q4_margin` still has missing values, raise error and stop.

## Health Metrics
- After running `evaluate.py`, check zeroed-prediction ratio in `results/predictions.csv`:
  ```python
  df = pd.read_csv("results/predictions.csv")
  ratio = (df["pred_delta_std"] > df["confidence_threshold"]).mean()
  ```
  - Normal: around 10% (observed)
  - Warning: >50% (model confidence degraded)

## Rules
- Keep feature definitions consistent across `prepare_data.py`, `train.py`, `evaluate.py`.
- If schema changes, verify compatibility with:
  - `strategies/predict_published.py`
  - `strategies/build_candidates.py`
- Do not commit model binaries and generated csv/json unless explicitly requested.
