# Stock Analysis Project — AI Assistant Guide

## First Step: Ask the User

When starting a session, **always ask the user which role you should take**:

1. **Frontend Engineer** — React/Next.js UI development
2. **Backend & Data Engineer** — FastAPI API development, scanner logic, backtest strategy, and complete data pipeline (scraper → processor → importer → calculator)

Then read the corresponding guide:

| Role | Guide File | Scope |
|------|-----------|-------|
| Frontend Engineer | `frontend/CLAUDE.md` | `frontend/` directory only |
| Backend & Data Engineer | `backend/CLAUDE.md` | `backend/`, `scanner/`, `strategy/`, `scraper/`, `processor/`, `importer/`, `calculator/`, `schedules/`, `common/` |

## Boundaries

Each role should **stay within its own scope**. If a task crosses boundaries, explicitly tell the user:

> "This requires changes in [other domain]. Please ask a [Frontend/Backend & Data] Engineer to handle that part."

Examples:
- Backend & Data engineer asked to change the chart UI → defer to Frontend Engineer
- Frontend engineer needs a new API endpoint or database changes → defer to Backend & Data Engineer

## Shared Infrastructure

These files are shared across roles. Be careful when modifying:

- `docker-compose.yml` — All services defined here
- `common/schemas.py` — **Single Source of Truth** for all database table schemas and data types (shared by processor, importer, and validator)
- `data/` — Shared data directory (raw → processed → DB)
- PostgreSQL schema — Changes affect both Data Engineer (importer) and Backend Engineer (queries)

## Project Overview

Taiwan stock market analysis platform:

- **Data pipeline**: Scrape TWSE/TPEx → process CSVs → import to PostgreSQL.
- **Analytics engine**: ML-based EPS prediction (v1-v4) and Point-in-Time (PIT) valuation analysis.
- **Backend API**: FastAPI serving market data, volume spike scanner, forward-looking valuations, and backtesting.
- **Frontend**: Next.js dashboard with candlestick charts, scanner UI, institutional charts

## How to Run

```bash
# 1. Start core services
docker compose up -d db backend frontend

# 2. Daily Data Update (ETL)
./schedules/daily_update.sh 20260211

# 3. Daily Analytics (Indicators & ML Valuations)
# This script handles technical indicators, trust_holding, dealer_holding, shareholding_concentration, and valuation_daily.
./schedules/daily_calculator.sh 20260211
```
