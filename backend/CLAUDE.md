# Backend & Data Pipeline Guide (for AI Assistants)

This guide covers two main areas:
1. **Backend API**: FastAPI backend serving the stock analysis frontend, integrating `scanner/` and `strategy/` modules
2. **Data Pipeline**: Complete ETL pipeline (scraper → processor → importer → calculator)

## Maintaining This Document

**After completing each task**, review this CLAUDE.md to ensure it remains consistent with the actual code. If you modified any behavior, schema, environment variable, or pipeline logic, update the relevant sections here. Keeping this document in sync with the codebase is essential for future AI assistants.

### 🔴 STRICT ENVIRONMENT CONSISTENCY RULE (CORE MANDATE)

**NEVER take shortcuts by manually copying files or relying solely on volume mounts for core logic updates.**
Whenever you modify code in `processor/`, `importer/`, `scraper/`, or `common/`, you **MUST** rebuild the corresponding Docker image:
```bash
docker compose build <service_name>
```
Failing to do this leads to "Host-Container desync" where the container runs old logic even though the host files look correct. This is especially critical for `processor` and `importer` which handle complex parsing and database schema logic.

---

# Part 1: Backend API

## Tech Stack

- **FastAPI** 0.110.0 + **Pydantic** 2.6.3
- **SQLAlchemy** 2.0.29 (raw SQL via `text()`, no ORM models)
- **PostgreSQL** 15 via psycopg2
- **Uvicorn** with `--reload` (auto-reload on file changes)

## Project Structure

```
backend/
├── main.py              # All endpoints, models, and app config
├── create_indexes.py    # DB index creation utility
├── Dockerfile
└── requirements.txt

scanner/                 # Imported by backend at runtime
├── volume_spike_scanner.py   # SQL-based volume spike detection
└── plot_candlestick.py       # CLI charting (not used by API)

strategy/                # Imported by backend at runtime
├── core.py              # Backtest engine (StrategyConfig, run_backtest)
└── __init__.py
```

## Running

```bash
# REBUILD after ANY code change to ensure consistency:
docker compose build backend && docker compose up -d backend

# Rebuild after changing Dockerfile or requirements.txt
docker compose up -d --build backend
```

## Raw Data API Tests

Raw endpoints have pytest coverage under `backend/tests/`.

**Prereqs (local venv):**
- `pytest`
- `sqlalchemy`
- `psycopg2-binary`
- `httpx`

**Run:**
```bash
./venv/bin/python -m pytest backend/tests -q
```

**Notes:**
- Tests query the real Postgres at `localhost:5432` (default envs in `backend/tests/conftest.py`).
- The tests sample the latest row per table and validate `/raw/*` endpoints, date format, required fields, and filters.

## IMPORTANT: File Path Gotcha (Live Reload)

The `backend` service uses a volume mount `./backend:/app` in `docker-compose.yml`. This maps your local `backend/` directory directly to `/app` in the container.

**This means:** 
- Editing `backend/main.py` on the host **DOES** trigger an auto-reload of the Uvicorn server (it's started with `--reload`).
- The `strategy/` and `scanner/` directories are also mounted (`./strategy:/app/strategy`, `./scanner:/app/scanner`), so changes there also reflect immediately.

**When to rebuild:** 
You only need to run `docker compose build backend` if you change `backend/requirements.txt` or the `backend/Dockerfile`.

**Note on other services:** 
The `processor` and `importer` services **DO NOT** use code volume mounts. You **MUST** rebuild them after any code change:
`docker compose build processor importer`

## Database Connection

```python
def get_db_url():
    # Env vars: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
    # Defaults: user, password, db, 5432, stock_db
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
```

All queries use raw SQL via `sqlalchemy.text()`. No ORM models — just `engine.connect()` + `conn.execute(sql, params)`.

## API Endpoints

### Scanner

| Endpoint | Method | Key Params | Response Model |
|----------|--------|-----------|----------------|
| `/scanner/volume-spike` | GET | `date` (YYYY-MM-DD), `min_volume` (5000000), `volume_ratio` (4.0), `avg_days` (10), `filter_long_shadow` (true) | `List[VolumeSpikeResult]` |
| `/scanner/candlestick/{symbol}` | GET | `date`, `days_before` (30), `days_after` (10) | `List[CandlestickData]` |
| `/scanner/institutional/{symbol}` | GET | `date`, `days_before` (90), `days_after` (90) | `List[InstitutionalData]` |

### Backtest

| Endpoint | Method | Body | Response Model |
|----------|--------|------|----------------|
| `/backtest/run` | POST | `BacktestRequest` JSON | `BacktestResult` |

### Market Data

| Endpoint | Method | Key Params | Response Model |
|----------|--------|-----------|----------------|
| `/quotes/top-volume` | GET | `date`, `limit` (10), `sort` (asc/desc) | `List[StockQuote]` |
| `/quotes/volume-breakout` | GET | `date`, `min_volume`, `ratio`, `limit` | `List[VolumeBreakoutQuote]` |
| `/analysis/ma` | GET | `date`, `limit`, `sort` | `List[MAQuote]` |
| `/analysis/vma` | GET | `date`, `limit`, `sort` | `List[VMAQuote]` |

### ML/RL Training Data

| Endpoint | Method | Key Params | Response Model |
|----------|--------|-----------|----------------|
| `/ml/training-data` | GET | `start_date`, `end_date`, `symbols` (optional), `include_indicators` (true), `include_institutional` (true) | `List[MLTrainingData]` |

**Purpose:** Bulk historical data endpoint for Machine Learning / Reinforcement Learning training. Optimized for minimal API round-trips.

**Features:**
- Dynamic SQL with optional JOINs (only fetch what's needed)
- Supports filtering by symbols or returns all active stocks
- Results sorted by `date` and `symbol` for training pipeline efficiency
- Composite indexes for fast query performance

### Raw Data API (Direct Table Access)

| Endpoint | Method | Key Params | Response Model |
|----------|--------|-----------|----------------|
| `/raw/daily-quotes` | GET | `start_date`, `end_date`, `symbol?`, `market?`, `limit=1000`, `offset=0` | `List[DailyQuoteRaw]` |
| `/raw/margin-trading` | GET | Same as above | `List[MarginTradingRaw]` |
| `/raw/margin-summary` | GET | `start_date`, `end_date`, `market?`, `limit=1000`, `offset=0` | `List[MarginSummaryRaw]` |
| `/raw/institutional-investors`| GET | Same as daily-quotes | `List[InstitutionalInvestorsRaw]` |
| `/raw/institutional-summary` | GET | Same as margin-summary | `List[InstitutionalSummaryRaw]` |
| `/raw/foreign-holding` | GET | Same as daily-quotes | `List[ForeignHoldingRaw]` |
| `/raw/pe-ratio` | GET | Same as daily-quotes | `List[PeRatioRaw]` |
| `/raw/market-indices` | GET | Same as daily-quotes | `List[MarketIndexRaw]` |
| `/raw/monthly-revenue` | GET | Same as daily-quotes | `List[MonthlyRevenueRaw]` |
| `/raw/shareholding` | GET | Same as above (no market) | `List[ShareholdingRaw]` |
| `/raw/stock-info` | GET | `symbol?`, `industry?`, `market?`, `limit`, `offset` | `List[StockInfoRaw]` |
| `/raw/stock-tags` | GET | `symbol?`, `tag?`, `limit`, `offset` | `List[StockTagRaw]` |
| `/raw/quarterly-reports` | GET | `start_date` (YYYYQX), `end_date`, `symbol`, `limit`, `offset` | `List[QuarterlyReportRaw]` |
| `/raw/income-statements` | GET | Same as quarterly-reports | `List[IncomeStatementRaw]` |
| `/raw/balance-sheets` | GET | Same as quarterly-reports | `List[BalanceSheetRaw]` |
| `/raw/cash-flows` | GET | Same as quarterly-reports | `List[CashFlowRaw]` |

**Purpose:** Provides direct access to standardized "raw" data from every table in the database. 
- **Features:** Supports pagination via `limit` (max 5000) & `offset`. 
- **Data Integrity:** Automatically handles non-JSON values (NaN/Inf) by converting them to `null`.
- **Sorting:** Defaults to `date DESC` (and `symbol ASC` where applicable).
- **Date Format:** Financial statements (`quarterly-reports`, `income-statements`, etc.) use **`YYYYQX`** string format (e.g., `2025Q3`). Backend logic is optimized to preserve this format without automatic date conversion.

**Pagination Example:**
To fetch the first 1000 records:
`GET /raw/daily-quotes?start_date=2026-01-01&end_date=2026-01-31&limit=1000&offset=0`

To fetch the next 1000 records:
`GET /raw/daily-quotes?start_date=2026-01-01&end_date=2026-01-31&limit=1000&offset=1000`

### Health

| Endpoint | Method | Response |
|----------|--------|---------|
| `/health` | GET | `{"status": "ok", "db_connection": "success"}` |

## Pydantic Models (all in main.py)

### VolumeSpikeResult
```
symbol, name, date, open, high, low, close, volume, volume_ratio,
distance_from_high_pct?, upper_shadow_ratio?,
ma5?, ma10?, ma20?, ma60?, k?, d?, rsi6?, rsi12?, macd_dif?, macd_dea?
```

### CandlestickData
```
date, open, high, low, close, volume, ma5?, ma10?, ma20?, ma60?
```

### InstitutionalData
```
date, foreign_net, trust_net, foreign_held_shares?, trust_held_shares?
```
- `trust_held_shares` is a running sum of `trust_net` from earliest data (approx. value starting from 0 at 2022-01-03)
- Computed via CTE with `SUM(trust_net) OVER (ORDER BY date)` across ALL dates, then filtered to display range

### BacktestRequest
```
start_date, end_date, strategy_mode ("shares"|"amount"), capital (100000),
hold_days (3), allow_pyramiding (true), only_red_candle (false),
take_profit_pct (0.0), stop_loss_pct (0.0)
```

### BacktestResult
```
summary: { total_trades, total_profit, total_cost, roi, win_rate, avg_return }
trades: [{ symbol, name, buy_date, sell_date, buy_price, sell_price, shares, profit, return_rate }]
```

### MLTrainingData
```
date, symbol, open, high, low, close, volume,
ma5?, ma10?, ma20?, ma60?, ma120?, ma240?,
vma5?, vma10?, vma20?, vma60?,
k?, d?, rsi6?, rsi12?, macd_dif?, macd_dea?,
foreign_net?, trust_net?, dealer_net?, foreign_held_shares?, trust_held_shares?
```
- All fields with `?` are optional (null when `include_indicators=false` or `include_institutional=false`)
- `trust_held_shares` is computed as running sum of `trust_net` (similar to `foreign_held_shares`)
- Designed for ML/RL training with complete OHLCV + indicators + institutional data
- Supports bulk queries across multiple stocks and date ranges

### Raw Data Models

**Important Notes:**
- All `date` fields return YYYY-MM-DD format strings (not datetime objects)
- Database schema uses TEXT type for all date columns (standardized across 12 tables)
- All `symbol` fields use TEXT type (standardized across 10 tables)
- `bid` and `ask` fields in DailyQuoteRaw are strings (stored as TEXT in database)

**Models:**
- **DailyQuoteRaw**: date, symbol, name, market, open, high, low, close, volume, value, transactions, change, direction, bid, ask, pe_ratio
- **MarginTradingRaw**: date, symbol, name, market, margin_long_buy/sell/cash_repay/prev_balance/balance/limit, margin_short_buy/sell/cash_repay/prev_balance/balance/limit, offset_balance
- **MarginSummaryRaw**: date, market, item, buy, sell, cash_repay, prev_balance, today_balance
- **InstitutionalInvestorsRaw**: date, symbol, name, market, foreign_buy/sell/net, trust_buy/sell/net, dealer_buy/sell/net
- **InstitutionalSummaryRaw**: date, market, item, buy, sell, net
- **ForeignHoldingRaw**: date, symbol, market, issued_shares, available_shares, foreign_held_shares, available_pct, held_pct, limit_pct
- **PeRatioRaw**: date, symbol, market, pe_ratio, dividend_yield, pb_ratio
- **MarketIndexRaw**: date, symbol, name, market, close, change, change_pct
- **MonthlyRevenueRaw**: date, symbol, market, revenue_current, revenue_last_month/year, mom_pct, yoy_pct, accumulated_revenue, accumulated_revenue_last_year, accumulated_yoy_pct
- **ShareholdingRaw**: date, symbol, market, level, holders, shares, percentage
- **StockInfoRaw**: symbol, name, industry, market, listing_date, tags (array)
- **StockTagRaw**: symbol, tag
- **QuarterlyReportRaw**: date (YYYYQX), symbol, market, name, revenue, revenue_ly, revenue_yoy, op_income, op_income_ly, op_income_yoy, non_op_income, pretax_income, net_income, eps, eps_ly, eps_yoy, capital, nav_per_share, equity_to_assets_ratio, current_ratio, quick_ratio
- **IncomeStatementRaw**: date (YYYYQX), symbol, market, name, revenue, cost_of_revenue, gross_profit, operating_expense, operating_income, non_operating_income, pretax_income, tax_expense, net_income, eps, etc.
- **BalanceSheetRaw**: date (YYYYQX), symbol, market, name, current_assets, noncurrent_assets, total_assets, current_liabilities, total_liabilities, total_equity, share_capital, nav_per_share, etc.
- **CashFlowRaw**: date (YYYYQX), symbol, market, name, cash_flow_operating, cash_flow_investing, cash_flow_financing, net_cash_change, cash_begin, cash_end

## Database Tables Used

| Table | Key Columns | Used By |
|-------|------------|---------|
| `daily_quotes` | date, symbol, open, high, low, close, volume, name, market | Most endpoints |
| `technical_indicators` | date, symbol, ma5-ma240, vma5-vma240, k, d, rsi6, rsi12, macd_dif, macd_dea | Scanner, analysis, ML training |
| `institutional_investors` | date, symbol, foreign_net, trust_net, dealer_net | Institutional API, ML training |
| `foreign_holding` | date, symbol, foreign_held_shares | Institutional API, ML training |
| `margin_summary` | date, market, item, buy, sell, cash_repay, today_balance | Market analysis |

**Indexes:**
- `idx_daily_quotes_date_symbol`, `idx_daily_quotes_symbol_date` (daily_quotes)
- `idx_technical_indicators_symbol_date` (technical_indicators)
- `idx_institutional_investors_symbol_date` (institutional_investors)
- `idx_foreign_holding_symbol_date` (foreign_holding)

The composite indexes on `(symbol, date)` optimize JOIN performance for the ML training data endpoint.

## Scanner Filter Logic (volume-spike)

The scanner SQL in `scanner/volume_spike_scanner.py` applies these filters:
1. `volume >= min_volume` (default 5M shares)
2. `volume >= avg_volume_Nd * volume_ratio` (default 4x vs 10-day avg)
3. `close > open` (red candle / bullish close)
4. `close >= MA60` (above 60-day moving average; stocks without MA60 are excluded)
5. `close >= 90-day highest close` (near-term high)
6. Optional: upper shadow ratio < 1.0 (filter long upper shadows)

## Strategy / Backtest Logic

Located in `strategy/core.py`:
- **Signal**: `volume > vma10 * 5`
- **Entry**: Buy at next trading day's open
- **Exit**: Time-based (N days), take-profit, or stop-loss
- **Costs**: Commission 0.1425% + Tax 0.3% (Taiwan market standard)
- **Modes**: Fixed shares (1000/trade) or fixed capital amount

## CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Error Handling Pattern

All endpoints follow this pattern:
```python
try:
    # SQL query + data processing
    return data
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
    raise HTTPException(status_code=500, detail=str(e))
```

## Testing Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Volume spike scanner
curl "http://localhost:8000/scanner/volume-spike?date=2025-10-03"

# Candlestick chart data
curl "http://localhost:8000/scanner/candlestick/6548?date=2025-10-03"

# Institutional data
curl "http://localhost:8000/scanner/institutional/2330?date=2025-12-01"

# Backtest
curl -X POST http://localhost:8000/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2025-01-01","end_date":"2025-06-30","hold_days":3}'

# Top volume
curl "http://localhost:8000/quotes/top-volume?date=2025-10-03&limit=5"

# ML training data - specific stocks with all data
curl "http://localhost:8000/ml/training-data?start_date=2025-01-01&end_date=2025-01-31&symbols=2330,2317,2454"

# ML training data - all stocks for a single day
curl "http://localhost:8000/ml/training-data?start_date=2025-01-02&end_date=2025-01-02"

# ML training data - OHLCV only (no indicators or institutional)
curl "http://localhost:8000/ml/training-data?start_date=2025-01-01&end_date=2025-01-10&symbols=2330&include_indicators=false&include_institutional=false"

# --- Raw Data API Tests ---

# Get raw quotes for TSMC (2330) on a specific day
curl "http://localhost:8000/raw/daily-quotes?symbol=2330&start_date=2026-02-06&end_date=2026-02-06"

# Get raw margin trading balance for TSMC
curl "http://localhost:8000/raw/margin-trading?symbol=2330&start_date=2026-02-01&end_date=2026-02-06"

# Get raw institutional market summary
curl "http://localhost:8000/raw/institutional-summary?start_date=2026-02-06&end_date=2026-02-06"

# Get raw monthly revenue
curl "http://localhost:8000/raw/monthly-revenue?symbol=2330&start_date=2026-01-01&end_date=2026-01-01"

# Get raw quarterly reports (Uses YYYYQX format)
curl "http://localhost:8000/raw/quarterly-reports?symbol=2330&start_date=2024Q1&end_date=2025Q3"

# Get raw income statements
curl "http://localhost:8000/raw/income-statements?symbol=2330&start_date=2025Q3&end_date=2025Q3"

# Get raw balance sheets
curl "http://localhost:8000/raw/balance-sheets?symbol=2330&start_date=2025Q3&end_date=2025Q3"
```

## Adding a New Endpoint

1. Define Pydantic response model in `main.py`
2. Add endpoint function with `@app.get()` or `@app.post()`
3. Write raw SQL via `text()`, execute with `engine.connect()`
4. Map rows to Pydantic models
5. Rebuild: `docker compose up -d --build backend`

## Database Maintenance Best Practices

### Creating and Managing Indexes

**Critical Indexes:** The composite indexes listed in the "Database Tables Used" section are essential for API performance. If indexes are lost due to database operations:

1. **Verify indexes exist:**
   ```bash
   docker compose exec -T db psql -U user -d stock_db -c \
     "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'idx_%' ORDER BY tablename, indexname;"
   ```

2. **Recreate missing indexes:**
   ```bash
   docker compose run --rm backend python create_indexes.py
   ```

3. **Expected indexes (5 total):**
   - `idx_daily_quotes_date_symbol` (daily_quotes)
   - `idx_daily_quotes_symbol_date` (daily_quotes)
   - `idx_tech_symbol_date` (technical_indicators)
   - `idx_institutional_investors_symbol_date` (institutional_investors)
   - `idx_foreign_holding_symbol_date` (foreign_holding)

**Performance Impact:** Missing indexes can degrade query performance from ~50ms to several seconds for multi-table JOINs (e.g., ML training data endpoint).

**Prevention:**
- Always verify indexes after database maintenance operations
- Document any manual database schema changes
- Test critical endpoints after database operations

### Database Recovery Incidents

For historical database issues and resolutions, see `backend/requests.md` → Data Recovery Log section.

---

# Part 2: Data Pipeline Overview

The data pipeline fetches, processes, and loads Taiwan stock market data into PostgreSQL.

## Pipeline Architecture

```
scraper/     → Fetch raw CSV from TWSE/TPEx/MOPS/TDCC        [scraper/CLAUDE.md]
processor/   → Clean & standardize (CSV→standardized CSVs)     [processor/CLAUDE.md]
importer/    → Load into PostgreSQL (delete-before-insert)     [importer/CLAUDE.md]
calculator/  → Compute technical indicators                     [calculator/CLAUDE.md]
scripts/     → Orchestration (daily_update.sh)
common/      → Shared constants (CATEGORY_MAP)
```

**Module Documentation:**
- **Scraper**: See `scraper/CLAUDE.md` for data sources, scheduling, and fetch logic
- **Processor**: See `processor/CLAUDE.md` for v3.0 date-first architecture, error handling, and validation
- **Importer**: See `importer/CLAUDE.md` for database import behavior and filtering rules
- **Calculator**: See `calculator/CLAUDE.md` for technical indicator formulas and computation

## Daily Update Pipeline

```bash
# Run full pipeline for a specific date (Always BUILD before bulk runs to ensure logic sync)
docker compose build processor importer calculator
./scripts/daily_update.sh 20260201

# Manual steps (Use --rm for transient tasks):
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer
docker compose run --rm calculator
```

**Pipeline order**: scraper → processor (with integrated QC) → importer → calculator

**Important Notes**:
- Processor v3.0 uses date-first architecture with integrated quality checking (see `processor/CLAUDE.md`)
- Calculator processes all stocks, not just the specified date range (see `calculator/CLAUDE.md`)
- For detailed module behavior, see individual CLAUDE.md files in each directory

## Data Sources & Update Frequency

For detailed information about data sources, see `scraper/CLAUDE.md`.

| Source | Service | Update Frequency |
|--------|---------|------------------|
| TWSE/TPEx | `scraper-daily` | Daily (after market close, 21:00) |
| MOPS | `scraper-monthly` | Monthly (before 10th) |
| MOPS | `scraper-quarterly` | Quarterly (approx. 45 days after Q-end) |
| TDCC | `scraper-weekly` | Weekly (Sunday) |

## Directory Structure (Data)

```
data/
├── raw/                          # Scraper output (original CSVs)
│   ├── daily_quotes/date=YYYYMMDD/{sii,otc}.csv
│   ├── institutional_investors/date=YYYYMMDD/{sii,otc}.csv
│   ├── institutional_summary/date=YYYYMMDD/{sii,otc}.csv
│   ├── foreign_holding/date=YYYYMMDD/{sii,otc}.csv
│   ├── margin_trading/date=YYYYMMDD/{sii,otc}.csv
│   ├── margin_sbl/date=YYYYMMDD/{sii,otc}.csv
│   ├── pe_ratio/date=YYYYMMDD/{sii,otc}.csv
│   ├── monthly_revenue/date=YYYYMM01/market.csv
│   ├── income_statement/date=YYYYQX/{sii,otc}_*.csv
│   ├── balance_sheet/date=YYYYQX/{sii,otc}_*.csv
│   ├── cash_flow/date=YYYYQX/{sii,otc}_*.csv
│   ├── shareholding_div/date=YYYYMMDD/{symbol}.csv   # Per-stock format (2023/09~)
│   └── shareholding_div2/TDCC_OD_1-5_YYYYMMDD.csv   # All-in-one format (2020/01~2023/09)
├── processed/                    # Processor output (cleaned CSVs)
│   └── (same structure, standardized schemas)
└── postgres/                     # PostgreSQL data volume
```

## Environment Variables (Data Pipeline)

**Common Variables** (used by most pipeline services):

| Variable | Default | Description |
|----------|---------|-------------|
| `START_DATE` | today | YYYYMMDD format (or YYYYQX for quarterly) |
| `END_DATE` | today | YYYYMMDD format (or YYYYQX for quarterly) |
| `DB_HOST` | db | PostgreSQL host |
| `DB_USER` | user | Database user |
| `DB_PASSWORD` | password | Database password |
| `DB_NAME` | stock_db | Database name |
| `DB_PORT` | 5432 | Database port |

**Module-Specific Variables**:
- **Scraper**: `MARKET_TYPE`, `FETCH_DELAY`, `REVENUE_YEAR`, `REVENUE_MONTH`, `TDCC_DATE` (see `scraper/CLAUDE.md`)
- **Processor**: `FORCE_REPROCESS`, `DEBUG` (see `processor/CLAUDE.md`)
- **Importer**: `IMPORT_CATEGORY`, `FORCE_REIMPORT` (see `importer/CLAUDE.md`)

## Key Pipeline Behaviors

For detailed information, see individual module documentation:

1. **Incremental by default**: Processor and importer skip existing data (override with FORCE flags)
2. **Data filtering**: Importer excludes ETFs and preferred stocks (`importer/CLAUDE.md`)
3. **Quality checks**: Integrated into processor v3.0 (`processor/CLAUDE.md`)
4. **Technical indicators**: Calculator processes all stocks at once (`calculator/CLAUDE.md`)
5. **Rate limiting**: Scraper enforces delays between requests (`scraper/CLAUDE.md`)

## Common Data Pipeline Tasks

### Daily Update
```bash
# Full pipeline for a specific date
./scripts/daily_update.sh 20260201
```

### Batch Historical Import
```bash
# Process + import a full year
for date in $(python3 -c "
import pandas_market_calendars as mcal
cal = mcal.get_calendar('XTAI')
for d in cal.schedule('2022-01-01','2022-12-31').index:
    print(d.strftime('%Y%m%d'))
"); do
  START_DATE=$date END_DATE=$date docker compose run --rm processor
  START_DATE=$date END_DATE=$date docker compose run --rm importer
done
docker compose run --rm calculator
```

### Monthly Revenue
See `scraper/CLAUDE.md` for scraping, `processor/CLAUDE.md` for processing, `importer/CLAUDE.md` for importing.

### Quarterly Reports
See `scraper/CLAUDE.md` for scraping, `processor/CLAUDE.md` for processing, `importer/CLAUDE.md` for importing.

### TDCC Shareholding Data
See `scraper/CLAUDE.md` for detailed manual and automated steps.

### Force Recalculate Indicators
```bash
docker compose run --rm calculator
```
See `calculator/CLAUDE.md` for details.

## Docker Services Reference

| Service | Purpose | Documentation |
|---------|---------|---------------|
| `scraper-daily` | Fetch daily market data from TWSE/TPEx | `scraper/CLAUDE.md` |
| `scraper-weekly` | Fetch TDCC shareholding data | `scraper/CLAUDE.md` |
| `scraper-monthly` | Fetch monthly revenue from MOPS | `scraper/CLAUDE.md` |
| `scraper-quarterly` | Fetch quarterly reports from MOPS | `scraper/CLAUDE.md` |
| `processor` | Clean & standardize raw CSVs | `processor/CLAUDE.md` |
| `importer` | Load processed data into PostgreSQL | `importer/CLAUDE.md` |
| `calculator` | Compute technical indicators | `calculator/CLAUDE.md` |
| `backend` | FastAPI server (port 8000) | `backend/CLAUDE.md` (this file) |
| `frontend` | Next.js UI (port 3000) | `frontend/CLAUDE.md` |
| `db` | PostgreSQL database | N/A |

---

## Module Documentation Index

For detailed information about each component:

- **Backend API**: `backend/CLAUDE.md` (this file) - FastAPI endpoints, models, scanner logic
- **Scraper**: `scraper/CLAUDE.md` - Data sources, scheduling, automation
- **Processor**: `processor/CLAUDE.md` - v3.0 architecture, error handling, validation
- **Importer**: `importer/CLAUDE.md` - Database import behavior, filtering rules
- **Calculator**: `calculator/CLAUDE.md` - Technical indicator formulas, computation
- **Frontend**: `frontend/CLAUDE.md` - React/Next.js UI components, charts
