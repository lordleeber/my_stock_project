# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Taiwan stock market analysis platform: EPS prediction → ML stock selection → rolling backtest.

Full pipeline: scrape TWSE/TPEx/MOPS/TDCC → process → import into PostgreSQL → compute indicators → train EPS model → build strategy features → train LGBMRanker → backtest → serve via FastAPI + Next.js.

## Key Commands

### Virtual Environment
All Python scripts use the repo-local venv:
```bash
venv/bin/python3 <script.py>
```

### Backend API (Docker)
```bash
# Start backend (auto-reloads on code changes — no rebuild needed for main.py)
docker compose up -d backend

# Rebuild only when changing requirements.txt or Dockerfile
docker compose up -d --build backend

# Run tests
./venv/bin/python -m pytest backend/tests -q
# Or in container (recommended):
docker compose run --rm backend python -m pytest tests -q
```

### Data Pipeline (Docker)
```bash
# Full daily pipeline for a specific date
./schedules/daily_update.sh 20260201

# Manual step-by-step
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer python import_daily.py
docker compose run --rm calculator

# Other schedules
./schedules/weekly_update.sh
./schedules/monthly_update.sh
./schedules/quarterly_update.sh 2025Q3
./schedules/xbrl_update.sh
```

### ML Pipeline (Python, no Docker)
```bash
# EPS prediction model (train_eps/)
venv/bin/python3 train_eps/prepare_data.py   --year 2025 --month 10
venv/bin/python3 train_eps/train.py          --year 2025 --month 10
venv/bin/python3 train_eps/evaluate.py       --year 2025 --month 10
venv/bin/python3 train_eps/gate_and_publish.py --year 2025 --month 10
# Or one-command:
venv/bin/python3 train_eps/run_pipeline.py   --year 2025 --month 10

# Strategy features + selection model (strategies/)
venv/bin/python3 strategies/prepare_data.py      --year 2025 --month 10
venv/bin/python3 strategies/predict_published.py --year 2025 --month 10
venv/bin/python3 strategies/finalize_strategy.py --year 2025 --month 10

# Batch (historical)
venv/bin/python3 strategies/batch_prepare_data.py
venv/bin/python3 strategies/batch_predict_published.py
venv/bin/python3 strategies/batch_finalize_strategy.py

# Selection model training
venv/bin/python3 strategies/analyze_feature_returns.py
venv/bin/python3 strategies/batch_train_selection_model.py
venv/bin/python3 strategies/train_selection_model.py  # production (full data)

# Rolling backtest
venv/bin/python3 backtester/run_rolling.py \
  --start_year 2022 --start_month 7 \
  --end_year 2025 --end_month 10 \
  --top-n 10 --position-amount 100000
venv/bin/python3 backtester/summarize_range.py

# Monthly stock picks (production)
venv/bin/python3 backtester/score_candidates.py --year 2025 --month 10
```

### GCP Deployment
```bash
./scripts/deploy_gcp.sh YOUR_PROJECT_ID YOUR_BUCKET_NAME asia-east1
./scripts/upload_to_gcs.sh YOUR_BUCKET_NAME  # after adding new monthly data
```

## Architecture

### Module Map

| Directory | Role |
|-----------|------|
| `scraper/` | Fetch raw CSVs from TWSE/TPEx/MOPS/TDCC |
| `processor/` | Clean & standardize raw CSVs (v3.0 date-first architecture) |
| `importer/` | Load processed CSVs into PostgreSQL (delete-before-insert) |
| `calculator/` | Compute technical indicators, shareholding concentration, forward valuation |
| `train_eps/` | LightGBM EPS delta prediction pipeline |
| `strategies/` | Feature engineering, EPS prediction integration, LGBMRanker selection model |
| `backtester/` | Rolling walk-forward portfolio backtester |
| `backend/` | FastAPI — full data endpoints (local) |
| `backend_lite/` | FastAPI — `/selection/score` only (GCP Cloud Run) |
| `common/` | Shared schemas (`schemas.py`), constants (`CATEGORY_MAP`), HTTP client |
| `schedules/` | Orchestration shell scripts + macOS launchd plists |
| `scripts/` | GCP deploy & GCS upload scripts |
| `tools/` | One-off data maintenance utilities |

### Data Flow

```
TWSE/TPEx/MOPS/TDCC
    → scraper/ (raw CSVs in data/raw/)
    → processor/ (standardized CSVs in data/processed/)
    → importer/ (PostgreSQL stock_db)
    → calculator/ (technical_indicators, shareholding_concentration, valuation_daily)
    → train_eps/ (models_eps/<year>/<month>/)
    → strategies/ (strategies/output/<year>/<month>/dataset_strategy.csv)
    → models_selection/ (selection_model.pkl per month)
    → backtester/ (backtester/output/rolling/)
    → backend/ (FastAPI) → frontend/ (Next.js)
```

### GCP Architecture

```
Browser
  → Cloud Run: frontend (Next.js)
  → Cloud Run: backend-lite (FastAPI, /selection/score only)
  → Cloud Storage: strategies/output + models_selection artifacts
```
PostgreSQL stays local; models and CSVs are uploaded to GCS.

### Walk-Forward Design

- Selection models stored at `models_selection/<cutoff_year>/<cutoff_month>/selection_model.pkl`
- Backtest month M uses the latest model with cutoff < M (no look-ahead bias)
- EPS models stored at `models_eps/<year>/<month>/`

### Database

- PostgreSQL 15, default: `user/password@localhost:5432/stock_db`
- All `date` columns use **TEXT** type (not DATE) for consistency
- Symbols are 4-digit numeric strings stored as TEXT
- Date formats: daily → `YYYY-MM-DD`, quarterly → `YYYYQX`, monthly revenue → `YYYYMXX`
- Backend uses raw SQL via `sqlalchemy.text()` — no ORM models
- Connection env vars: `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`

## Critical Rules

### Docker Rebuild Rule
`processor`, `importer`, and `calculator` do **NOT** mount source code. After any code change in those directories:
```bash
docker compose build processor importer calculator
```
`backend` uses a volume mount and auto-reloads via uvicorn `--reload` — only rebuild if `requirements.txt` or `Dockerfile` changes.

### DB Schema Changes
Sync all schema changes to `common/schemas.py`.

### backend vs backend_lite
`backend_lite/` and `backend/` share the `/selection/score` endpoint logic — keep them in sync.

### Artifacts
Do not commit generated `.csv`, `.json`, `.pkl` artifacts unless explicitly requested.

## Sub-Module Documentation

Each major component has its own `CLAUDE.md` with detailed field-level specs:

- `backend/CLAUDE.md` — all API endpoints, Pydantic models, raw data API date formats, DB indexes
- `calculator/CLAUDE.md` — indicator formulas, PIT valuation logic, `valuation_daily` schema
- `scraper/CLAUDE.md` — data sources, scheduling windows, fetch logic
- `processor/CLAUDE.md` — v3.0 date-first architecture, QC, error handling
- `importer/CLAUDE.md` — import behavior, ETF/preferred stock filtering
- `schedules/CLAUDE.md` — launchd setup, manual run commands
- `train_eps/CLAUDE.md` — EPS model training calendar, gate rules, feature contracts
- `strategies/README.md` — hard filters, `dataset_strategy.csv` field reference, ML model spec
