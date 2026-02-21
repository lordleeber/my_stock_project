# train_eps

`train_eps` handles EPS model workflow: data preparation, training, evaluation, and publish gate.

## Directory Convention
- Training data and artifacts:
  - `train_eps/sii/<year>/<month>/`
  - `train_eps/otc/<year>/<month>/`
- Published models:
  - `models_eps/sii/<year>/<month>/`
  - `models_eps/otc/<year>/<month>/`

## Shared Scripts
- `train_eps/train.py`
- `train_eps/evaluate.py`
- `train_eps/gate_and_publish.py`

## Standard Flow
1. Run month-specific `prepare_data.py`
2. Run shared `train.py`
3. Run shared `evaluate.py`
4. Run `gate_and_publish.py` (publish only when gate passes)

## Example: SII 2025/08
```powershell
.\.venv\Scripts\python.exe train_eps\sii\2025\08\prepare_data.py --data-source api
.\.venv\Scripts\python.exe train_eps\train.py --month-dir train_eps\sii\2025\08 --n-jobs 1
.\.venv\Scripts\python.exe train_eps\evaluate.py --month-dir train_eps\sii\2025\08 --n-jobs 1
.\.venv\Scripts\python.exe train_eps\gate_and_publish.py --month-dir train_eps\sii\2025\08 --models-root models_eps
```

## Example: SII 2025/09
```powershell
.\.venv\Scripts\python.exe train_eps\sii\2025\09\prepare_data.py --data-source api
.\.venv\Scripts\python.exe train_eps\train.py --month-dir train_eps\sii\2025\09 --n-jobs 1
.\.venv\Scripts\python.exe train_eps\evaluate.py --month-dir train_eps\sii\2025\09 --n-jobs 1
.\.venv\Scripts\python.exe train_eps\gate_and_publish.py --month-dir train_eps\sii\2025\09 --models-root models_eps
```

## Gate Rule (Default)
- Compare `rf_delta` vs `baseline_q2_eps`
- Metric: `mae`
- Publish condition: `primary <= baseline * 0.95`

## Main Outputs
- In month directory (example `train_eps/sii/2025/09/`):
  - `dataset_train.csv`
  - `dataset_evaluate.csv`
  - `dataset_meta.csv`
  - `model.pkl`
  - `train_metrics.json`
  - `results/evaluate_by_fold.csv`
  - `gate_result.json`
- In published model directory (example `models_eps/sii/2025/09/`):
  - `<timestamp>.pkl`
  - `<timestamp>.json`
  - `latest.json`

## Notes
- `prepare_data.py --data-source api` uses backend API.
- Without `--data-source`, default is DB mode (`DB_HOST` must be reachable).
- Generated csv/json/pkl files are not committed unless explicitly requested.
