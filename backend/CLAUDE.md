# Backend & Data Pipeline Guide (for AI Assistants)

This guide covers two main areas:
1. **Backend API**: FastAPI backend serving the stock analysis frontend, integrating `scanner/` and `strategy/` modules
2. **Data Pipeline**: Complete ETL pipeline (scraper → processor → importer → calculator)

## Maintaining This Document

**After completing each task**, review this CLAUDE.md to ensure it remains consistent with the actual code. If you modified any behavior, schema, environment variable, or pipeline logic, update the relevant sections here. Keeping this document in sync with the codebase is essential for future AI assistants.

### 🔴 STRICT ENVIRONMENT CONSISTENCY RULE (CORE MANDATE)

**NEVER take shortcuts by manually copying files or relying solely on volume mounts for core logic updates.**
Whenever you modify code in `processor/`, `importer/`, `calculator/`, `scraper/`, or `common/`, you **MUST** rebuild the corresponding Docker image:
```bash
docker compose build <service_name>
```
Failing to do this leads to "Host-Container desync" where the container runs old logic even though the host files look correct. This is especially critical for `processor`, `importer`, and `calculator`.

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

# Container (recommended for env consistency)
docker compose run --rm backend python -m pytest tests -q
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
The `processor`, `importer`, and `calculator` services **DO NOT** use code volume mounts. You **MUST** rebuild them after any code change:
`docker compose build processor importer calculator`

## Database Connection

```python
def get_db_url():
    # Env vars: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
    # Defaults: user, password, db, 5432, stock_db
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
```

All queries use raw SQL via `sqlalchemy.text()`. No ORM models — just `engine.connect()` + `conn.execute(sql, params)`.

## API Endpoints


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

AI assistant guardrails:
- Do use `/raw/...` routes with `start_date` and `end_date`.
- Don't use `/api/raw/...` or `date_from` / `date_to` for backend raw endpoints.
- Date formats:
  - Daily-style endpoints (including `/raw/shareholding`, `/raw/valuation-analysis`): `YYYY-MM-DD`
  - `/raw/monthly-revenue`: `YYYYMXX` (example: `2026M01`)
  - Quarterly endpoints (`/raw/quarterly-reports`, `/raw/income-statements`, `/raw/balance-sheets`, `/raw/cash-flows`, `/raw/income-statements-xbrl`, `/raw/balance-sheets-xbrl`, `/raw/cash-flows-xbrl`): `YYYYQX` (example: `2025Q1`)
- Quick valid examples:
  - `GET /raw/shareholding?symbol=2308&start_date=2026-01-30&end_date=2026-01-30`
  - `GET /raw/monthly-revenue?symbol=2330&start_date=2026M01&end_date=2026M01`
  - `GET /raw/quarterly-reports?symbol=2330&start_date=2025Q1&end_date=2025Q1`

| Endpoint | Method | Key Params | Response Model |
|----------|--------|-----------|----------------|
| `/raw/daily-quotes` | GET | `start_date`, `end_date`, `symbol?`, `market?`, `limit=1000`, `offset=0` | `List[DailyQuoteRaw]` |
| `/raw/margin-trading` | GET | Same as above | `List[MarginTradingRaw]` |
| `/raw/margin-summary` | GET | `start_date`, `end_date`, `market?`, `limit=1000`, `offset=0` | `List[MarginSummaryRaw]` |
| `/raw/institutional-investors`| GET | Same as daily-quotes | `List[InstitutionalInvestorsRaw]` |
| `/raw/institutional-summary` | GET | Same as margin-summary | `List[InstitutionalSummaryRaw]` |
| `/raw/foreign-holding` | GET | Same as daily-quotes | `List[ForeignHoldingRaw]` |
| `/raw/trust-holding` | GET | Same as daily-quotes | `List[TrustHoldingRaw]` |
| `/raw/dealer-holding` | GET | Same as daily-quotes | `List[DealerHoldingRaw]` |
| `/raw/pe-ratio` | GET | Same as daily-quotes | `List[PeRatioRaw]` |
| `/raw/valuation-analysis` | GET | `start_date`, `end_date`, `symbol?`, `limit=1000`, `offset=0` | `List[ValuationAnalysisRaw]` |
| `/raw/market-indices` | GET | Same as daily-quotes | `List[MarketIndexRaw]` |
| `/raw/monthly-revenue` | GET | Same as daily-quotes | `List[MonthlyRevenueRaw]` |
| `/raw/shareholding` | GET | Same as above (no market) | `List[ShareholdingRaw]` |
| `/raw/shareholding-concentration` | GET | Same as above (no market) | `List[ShareholdingConcentrationRaw]` |
| `/raw/short-interest-analysis` | GET | `start_date`, `end_date`, `symbol?`, `market?`, `limit=1000`, `offset=0` | `List[ShortInterestAnalysisRaw]` |
| `/raw/margin-pressure-analysis` | GET | `start_date`, `end_date`, `symbol?`, `market?`, `limit=1000`, `offset=0` | `List[MarginPressureAnalysisRaw]` |
| `/raw/stock-info` | GET | `symbol?`, `industry?`, `market?`, `limit`, `offset` | `List[StockInfoRaw]` |
| `/raw/stock-tags` | GET | `symbol?`, `tag?`, `limit`, `offset` | `List[StockTagRaw]` |
| `/raw/dividend` | GET | `start_date`, `end_date`, `symbol?`, `limit`, `offset` | `List[DividendRaw]` |
| `/raw/quarterly-reports` | GET | `start_date` (YYYYQX), `end_date`, `symbol`, `limit`, `offset` | `List[QuarterlyReportRaw]` |
| `/raw/income-statements` | GET | Same as quarterly-reports | `List[IncomeStatementRaw]` |
| `/raw/balance-sheets` | GET | Same as quarterly-reports | `List[BalanceSheetRaw]` |
| `/raw/cash-flows` | GET | Same as quarterly-reports | `List[CashFlowRaw]` |
| `/raw/income-statements-xbrl` | GET | `start_date` (YYYYQX), `end_date`, `symbol?`, `limit`, `offset` | `List[XbrlStatementRaw]` |
| `/raw/balance-sheets-xbrl` | GET | Same as income-statements-xbrl | `List[XbrlStatementRaw]` |
| `/raw/cash-flows-xbrl` | GET | Same as income-statements-xbrl | `List[XbrlStatementRaw]` |

**Purpose:** Provides direct access to standardized "raw" data from every table in the database. 
- **Features:** Supports pagination via `limit` (max 5000) & `offset`. 
- **Data Integrity:** Automatically handles non-JSON values (NaN/Inf) by converting them to `null`.
- **Sorting:** Defaults to `date DESC` (and `symbol ASC` where applicable).
- **Date Format:** Financial statements (including XBRL statement endpoints) use **`YYYYQX`** string format (e.g., `2025Q3`). Backend logic is optimized to preserve this format without automatic date conversion.

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
foreign_streak_days?, trust_streak_days?, dealer_streak_days?,
foreign_net?, trust_net?, dealer_net?, foreign_held_shares?, trust_held_shares?
large_holder_ratio?, small_holder_ratio?, concentration_spread?,
large_holder_ratio_wow?, small_holder_ratio_wow?, concentration_spread_wow?
```
- All fields with `?` are optional (null when `include_indicators=false` or `include_institutional=false`)
- `trust_held_shares` is computed as running sum of `trust_net` (similar to `foreign_held_shares`)
- `*_streak_days` are streak counters derived from institutional net flow:
  - `net > 0` => positive streak days
  - `net < 0` => negative streak days
  - `net = 0` => `0` (does not distinguish no-trade vs buy=sell)
- Designed for ML/RL training with complete OHLCV + indicators + institutional data
- Supports bulk queries across multiple stocks and date ranges

### Raw Data Models

**Important Notes:**
- `date` fields are returned as strings (not datetime objects)
- Most raw tables use `YYYY-MM-DD`; quarterly and XBRL statement tables use `YYYYQX`; monthly revenue uses `YYYYMXX`
- Database schema uses TEXT type for all date columns across raw tables
- All `symbol` fields use **TEXT** type and strictly contain **4-digit numeric symbols** only.
- `bid` and `ask` fields in DailyQuoteRaw are strings (stored as TEXT in database)
- **DailyQuoteRaw** no longer contains `pe_ratio`. Use the standalone `pe_ratio` endpoint for valuation data.

**Models:**
- **DailyQuoteRaw**: date, symbol, name, market, open, high, low, close, volume, value, transactions, change, direction, bid, ask
- **MarginTradingRaw**: date, symbol, name, market, margin_long_buy/sell/cash_repay/prev_balance/balance/limit, margin_short_buy/sell/cash_repay/prev_balance/balance/limit, offset_balance
- **MarginSummaryRaw**: date, market, item, buy, sell, cash_repay, prev_balance, today_balance
- **InstitutionalInvestorsRaw**: date, symbol, name, market, foreign_buy/sell/net, trust_buy/sell/net, dealer_buy/sell/net
- **InstitutionalSummaryRaw**: date, market, institution, buy, sell, net
- **ForeignHoldingRaw**: date, symbol, market, issued_shares, available_shares, foreign_held_shares, available_pct, held_pct, limit_pct
- **TrustHoldingRaw**: date, symbol, market, trust_held_shares, issued_shares, trust_held_ratio
- **DealerHoldingRaw**: date, symbol, market, dealer_held_shares, issued_shares, dealer_held_ratio
- **PeRatioRaw**: date, symbol, market, pe_ratio, dividend_yield, pb_ratio
- **ValuationAnalysisRaw**: date, symbol, close, ttm_eps, pe_ratio_calculated, pe_ratio_from_pe_table, pe_percentile
- **MarketIndexRaw**: date, symbol, name, market, close, change, change_pct
- **MonthlyRevenueRaw**: date, symbol, market, revenue_current, revenue_last_month/year, mom_pct, yoy_pct, accumulated_revenue, accumulated_revenue_last_year, accumulated_yoy_pct, comment, publish_time
- **ShareholdingRaw**: date, symbol, level, level_name, holders, shares, percentage
- **ShareholdingConcentrationRaw**: date, symbol, large_holder_ratio, small_holder_ratio, concentration_spread, large_holder_count, small_holder_count, large_holder_ratio_wow, small_holder_ratio_wow, concentration_spread_wow
- **ShortInterestAnalysisRaw**: date, symbol, market, name, sbl_balance, sbl_balance_wow, sbl_balance_wow_pct, sbl_sell, sbl_repay, sbl_sell_repay_ratio, margin_short_balance, margin_short_balance_wow, margin_short_balance_wow_pct, short_pressure_score
- **MarginPressureAnalysisRaw**: date, symbol, market, name, margin_long_balance, margin_long_limit, margin_usage_ratio, margin_long_balance_wow, margin_long_balance_wow_pct, margin_short_balance, margin_short_limit, short_usage_ratio, margin_short_balance_wow, margin_short_balance_wow_pct, short_cover_pressure, margin_pressure_score
- **StockInfoRaw**: symbol, name, industry, market, listing_date, tags (array)
- **StockTagRaw**: symbol, tag
- **DividendRaw**: date, symbol, name, close_before, ref_price, rights_dividend_value, type
- **QuarterlyReportRaw**: date (YYYYQX), symbol, market, name, revenue_q/acc/acc_ly/acc_yoy, op_income_q/acc/acc_ly/acc_yoy, net_income_q/acc/acc_ly/acc_yoy, eps_q/acc/acc_ly/acc_yoy, capital, nav_per_share, etc.
- **IncomeStatementRaw**: date (YYYYQX), symbol, market, name, revenue_q/acc, cost_of_revenue_q/acc, gross_profit_q/acc, operating_income_q/acc, net_income_q/acc, eps_q/acc, etc.
- **BalanceSheetRaw**: date (YYYYQX), symbol, market, name, current_assets, total_assets, total_equity, share_capital, nav_per_share, etc. (No _q/_acc needed for snapshot data).
- **CashFlowRaw**: date (YYYYQX), symbol, market, name, cash_flow_operating_q/acc, cash_flow_investing_q/acc, cash_flow_financing_q/acc, net_cash_change_q/acc, cash_begin, cash_end
- **XbrlStatementRaw**: date (YYYYQX), symbol, period, period_type (`quarter`/`accumulated`/`as_of`), account_code, value_text, value_num

## Database Tables Used

| Table | Key Columns | Used By |
|-------|------------|---------|
| `daily_quotes` | date, symbol, open, high, low, close, volume, name, market | Most endpoints |
| `technical_indicators` | date, symbol, ma5-ma240, vma5-vma240, k, d, rsi6, rsi12, macd_dif, macd_dea, foreign_streak_days, trust_streak_days, dealer_streak_days | Scanner, analysis, ML training |
| `institutional_investors` | date, symbol, foreign_net, trust_net, dealer_net | Institutional API, ML training |
| `foreign_holding` | date, symbol, foreign_held_shares | Institutional API, ML training |
| `trust_holding` | date, symbol, trust_held_shares, trust_held_ratio | Raw API (`/raw/trust-holding`) |
| `dealer_holding` | date, symbol, dealer_held_shares, dealer_held_ratio | Raw API (`/raw/dealer-holding`) |
| `shareholding_concentration` | date, symbol, large_holder_ratio, small_holder_ratio, concentration_spread | Raw API (`/raw/shareholding-concentration`), ML training |
| `short_interest_analysis` | date, symbol, market, sbl/margin short metrics, short_pressure_score | Raw API (`/raw/short-interest-analysis`) |
| `margin_pressure_analysis` | date, symbol, market, margin usage/cover pressure metrics | Raw API (`/raw/margin-pressure-analysis`) |
| `margin_summary` | date, market, item, buy, sell, cash_repay, today_balance | Market analysis |
| `income_statement_xbrl` | date, symbol, period, period_type, account_code, value_text, value_num | Raw API (`/raw/income-statements-xbrl`) |
| `balance_sheet_xbrl` | date, symbol, period, period_type, account_code, value_text, value_num | Raw API (`/raw/balance-sheets-xbrl`) |
| `cash_flow_xbrl` | date, symbol, period, period_type, account_code, value_text, value_num | Raw API (`/raw/cash-flows-xbrl`) |

**Indexes:**
- `idx_daily_quotes_date_symbol`, `idx_daily_quotes_symbol_date` (daily_quotes)
- `idx_technical_indicators_symbol_date` (technical_indicators)
- `idx_institutional_investors_symbol_date` (institutional_investors)
- `idx_foreign_holding_symbol_date` (foreign_holding)
- `idx_trust_holding_symbol_date` (trust_holding)
- `idx_dealer_holding_symbol_date` (dealer_holding)
- `idx_shareholding_concentration_symbol_date` (shareholding_concentration)
- `idx_short_interest_analysis_symbol_date` (short_interest_analysis)
- `idx_margin_pressure_analysis_symbol_date` (margin_pressure_analysis)

The composite indexes on `(symbol, date)` optimize JOIN performance for the ML training data endpoint.


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
curl "http://localhost:8000/raw/monthly-revenue?symbol=2330&start_date=2026M01&end_date=2026M01"

# Get valuation analysis (daily format)
curl "http://localhost:8000/raw/valuation-analysis?symbol=2330&start_date=2026-02-01&end_date=2026-02-11&limit=2"

# Get raw quarterly reports (Uses YYYYQX format)
curl "http://localhost:8000/raw/quarterly-reports?symbol=2330&start_date=2024Q1&end_date=2025Q3"

# Get raw income statements
curl "http://localhost:8000/raw/income-statements?symbol=2330&start_date=2025Q3&end_date=2025Q3"

# Get raw balance sheets
curl "http://localhost:8000/raw/balance-sheets?symbol=2330&start_date=2025Q3&end_date=2025Q3"

# Get raw income statement XBRL rows
curl "http://localhost:8000/raw/income-statements-xbrl?symbol=2330&start_date=2025Q3&end_date=2025Q3&limit=5"

# Get raw balance sheet XBRL rows
curl "http://localhost:8000/raw/balance-sheets-xbrl?symbol=2330&start_date=2025Q3&end_date=2025Q3&limit=5"

# Get raw cash flow XBRL rows
curl "http://localhost:8000/raw/cash-flows-xbrl?symbol=2330&start_date=2025Q3&end_date=2025Q3&limit=5"
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

3. **Expected indexes (10 total):**
   - `idx_daily_quotes_date_symbol` (daily_quotes)
   - `idx_daily_quotes_symbol_date` (daily_quotes)
   - `idx_technical_indicators_symbol_date` (technical_indicators)
   - `idx_institutional_investors_symbol_date` (institutional_investors)
   - `idx_foreign_holding_symbol_date` (foreign_holding)
   - `idx_trust_holding_symbol_date` (trust_holding)
   - `idx_dealer_holding_symbol_date` (dealer_holding)
   - `idx_shareholding_concentration_symbol_date` (shareholding_concentration)
   - `idx_short_interest_analysis_symbol_date` (short_interest_analysis)
   - `idx_margin_pressure_analysis_symbol_date` (margin_pressure_analysis)

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
schedules/   → Orchestration (daily_update.sh)
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
./schedules/daily_update.sh 20260201

# Manual steps (Use --rm for transient tasks):
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer python import_daily.py
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
| TWSE/TPEx | `scraper-daily` | Daily (after market close, 22:00) |
| MOPS | `scraper-monthly` | Daily during month day 1~15 (updates previous month cumulatively) |
| MOPS | `scraper-quarterly` | Quarterly (approx. 45 days after Q-end) |
| TDCC | `scraper-weekly` | Weekly (Saturday) |

## Directory Structure (Data)

```
data/
├── raw/                          # Scraper output (original CSVs)
│   ├── <daily_category>/YYYY/YYYYMMDD/{sii,otc}.csv
│   ├── monthly_revenue/YYYY/YYYYMXX/tmp.csv
│   ├── monthly_revenue/YYYY/YYYYMXX/market.csv
│   ├── quarterly_reports/YYYY/YYYYQX/{sii,otc}.{xls,csv}
│   ├── income_statement/YYYY/YYYYQX/{sii,otc}_*.csv
│   ├── balance_sheet/YYYY/YYYYQX/{sii,otc}_*.csv
│   ├── cash_flow/YYYY/YYYYQX/{sii,otc}_*.csv
│   └── shareholding/YYYY/TDCC_OD_1-5_YYYYMMDD.csv
├── processed/                    # Processor output (cleaned CSVs)
│   └── category-specific normalized CSV outputs
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
- **Importer**: frequency entry points (`import_daily.py`, `import_weekly.py`, `import_monthly.py`, `import_quarterly.py`) and `FORCE_REIMPORT` (see `importer/CLAUDE.md`)

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
./schedules/daily_update.sh 20260201
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
  START_DATE=$date END_DATE=$date docker compose run --rm importer python import_daily.py
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
