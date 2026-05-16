# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Taiwan stock market analysis platform: EPS prediction → ML stock selection → rolling backtest.

Full pipeline: scrape TWSE/TPEx/MOPS/TDCC → process → import into PostgreSQL → compute indicators → train EPS model → build strategy features → train LGBMRanker → backtest → serve via FastAPI.

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
./schedules/xbrl_scrape_daily.sh           # 季報 XBRL 每日 scrape（launchd 排程亦走這支；不入庫）
./schedules/xbrl_process_import.sh         # 季報 XBRL process+import（公告期末/補資料；前提是 raw 已存在）
./schedules/xbrl_process_import.sh 2025Q4  # 指定季別
```

> 季報舊路徑（`quarterly_reports`/`income_statement`/`balance_sheet`/`cash_flow` 寫入）已 deprecated。所有季報資料一律改走 XBRL（`*_xbrl` 表）。舊版程式碼保留在各模組 `_deprecated/`，DB 舊表保留為 archive 不再更新。

### ML Pipeline (Python, no Docker)
```bash
# EPS prediction model (train_eps/)
venv/bin/python3 train_eps/step1_prepare_data.py          --year 2025 --month 10
venv/bin/python3 train_eps/step2_train.py                 --year 2025 --month 10
venv/bin/python3 train_eps/step3_evaluate.py              --year 2025 --month 10
venv/bin/python3 train_eps/step4_predict_and_publish.py   --year 2025 --month 10
# Or one-command:
venv/bin/python3 train_eps/run_pipeline.py                --year 2025 --month 10

# Batch evaluate / predict (historical)
venv/bin/python3 train_eps/step3_batch_evaluate.py
venv/bin/python3 train_eps/step4_batch_predict_and_publish.py

# Strategy features + selection model (strategies/)
venv/bin/python3 strategies/step1_prepare_data.py      --year 2025 --month 10
venv/bin/python3 strategies/step2_finalize_strategy.py --year 2025 --month 10

# Batch (historical)
venv/bin/python3 strategies/step1_batch_prepare_data.py
venv/bin/python3 strategies/step2_batch_finalize_strategy.py

# Selection model training
venv/bin/python3 strategies/step3_analyze_feature_returns.py
venv/bin/python3 strategies/step4_batch_train_selection_model.py
venv/bin/python3 strategies/step4_train_selection_model.py  # production (full data)

# Score candidates (production picks — run after step4)
venv/bin/python3 strategies/step5_score_and_publish.py --year 2025 --month 10
venv/bin/python3 strategies/step5_batch_score_and_publish.py  # batch all months

# Rolling backtest
venv/bin/python3 backtester/run_rolling.py \
  --start_year 2022 --start_month 7 \
  --end_year 2025 --end_month 10 \
  --top-n 10 --position-amount 100000
venv/bin/python3 backtester/summarize_range.py
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
| `common/` | Shared schemas (`schemas.py`), constants (`CATEGORY_MAP`), HTTP client |
| `schedules/` | Orchestration shell scripts + macOS launchd plists |
| `scripts/` | GCS upload scripts |
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
    → backend/ (FastAPI)
```

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
- `strategies/CLAUDE.md` — pipeline layout, XBRL table dependencies, anchor cash-flow conversion, step1 filters, walk-forward ordering
- `backtester/CLAUDE.md` — rolling_monthly.csv column semantics (cohort vs rotation), still-open handling
- `MONTHLY_PLAYBOOK.md` — 每月公告日後的 ML pipeline 作業流程（train_eps + strategies + selection model）
