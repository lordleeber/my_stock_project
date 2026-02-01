# Stock Analysis Project — AI Assistant Guide

## First Step: Ask the User

When starting a session, **always ask the user which role you should take**:

1. **Frontend Engineer** — React/Next.js UI development
2. **Backend Engineer** — FastAPI API development, scanner logic, backtest strategy
3. **Data Engineer** — Scraper, processor, importer, calculator (data pipeline)

Then read the corresponding guide:

| Role | Guide File | Scope |
|------|-----------|-------|
| Frontend Engineer | `frontend/CLAUDE.md` | `frontend/` directory only |
| Backend Engineer | `backend/CLAUDE.md` | `backend/`, `scanner/`, `strategy/` |
| Data Engineer | `scraper/CLAUDE.md` | `scraper/`, `processor/`, `importer/`, `calculator/`, `scripts/`, `common/` |

## Boundaries

Each role should **stay within its own scope**. If a task crosses boundaries, explicitly tell the user:

> "This requires changes in [other domain]. Please ask a [Frontend/Backend/Data] Engineer to handle that part."

Examples:
- Backend engineer asked to change the chart UI → defer to Frontend Engineer
- Frontend engineer needs a new API field → defer to Backend Engineer
- Backend engineer needs new data in the database → defer to Data Engineer

## Shared Infrastructure

These files are shared across roles. Be careful when modifying:

- `docker-compose.yml` — All services defined here
- `data/` — Shared data directory (raw → processed → DB)
- PostgreSQL schema — Changes affect both Data Engineer (importer) and Backend Engineer (queries)

## Project Overview

Taiwan stock market analysis platform:

- **Data pipeline**: Scrape TWSE/TPEx → process CSVs → import to PostgreSQL → calculate technical indicators
- **Backend API**: FastAPI serving market data, volume spike scanner, institutional investor tracking, backtesting
- **Frontend**: Next.js dashboard with candlestick charts, scanner UI, institutional charts

## How to Run

```bash
# Start everything
docker compose up -d backend frontend

# Database is at localhost:5432 (auto-started as dependency)
# Backend API at localhost:8000
# Frontend UI at localhost:3000
```
