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

## Per-Month Data Files
- `dataset_train.csv`
- `dataset_evaluate.csv`
- `dataset_meta.csv`

## Standard Flow
1. Run month-specific `prepare_data.py`
2. Run `train.py --month-dir train_eps/<market>/<year>/<month>`
3. Run `evaluate.py --month-dir train_eps/<market>/<year>/<month>`
4. Run `gate_and_publish.py --month-dir train_eps/<market>/<year>/<month>`

## Data Source
- `prepare_data.py` defaults to DB mode (`--data-source db`, usually `DB_HOST=db`).
- API mode is available with `--data-source api`.

## Publish Rule
- Only gate-passed models are published to `models_eps/<market>/<year>/<month>/`.
- Published artifacts include:
  - `<timestamp>.pkl`
  - `<timestamp>.json`
  - `latest.json`

## Typical Commands
```powershell
.\.venv\Scripts\python.exe train_eps\sii\2025\10\prepare_data.py --data-source api
.\.venv\Scripts\python.exe train_eps\train.py --month-dir train_eps\sii\2025\10 --n-jobs 1
.\.venv\Scripts\python.exe train_eps\evaluate.py --month-dir train_eps\sii\2025\10 --n-jobs -1
.\.venv\Scripts\python.exe train_eps\gate_and_publish.py --month-dir train_eps\sii\2025\10 --models-root models_eps
```

## Health Metrics
- After running `evaluate.py`, check the zeroed-prediction ratio in `results/predictions.csv`:
  ```python
  df = pd.read_csv("results/predictions.csv")
  ratio = (df["pred_delta_std"] > df["confidence_threshold"]).mean()
  ```
  - ✅ Normal: ratio ≈ 10% (observed value)
  - ⚠️ Warning: ratio > 50% — model lost confidence in most stocks; check feature distribution or retrain.

## Rules
- Keep feature definitions consistent across train/evaluate.
- If schema changes, verify compatibility with:
  - `strategies/predict_published.py`
  - `strategies/build_candidates.py`
- Do not commit model binaries and generated csv/json unless explicitly requested.

