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
- **StockInfoRaw**: symbol, name, industry, market, listing_date
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

# Part 2: Data Pipeline

The data pipeline fetches, processes, and loads Taiwan stock market data into PostgreSQL.

## Pipeline Architecture

```
scraper/     → Fetch raw CSV from TWSE/TPEx/MOPS/TDCC
processor/   → Clean & standardize (Chinese→English columns, numeric conversion)
importer/    → Load into PostgreSQL (delete-before-insert, dedup by date+market)
calculator/  → Compute technical indicators (MA, KD, RSI, MACD, Bollinger)
scripts/     → Orchestration (daily_update.sh)
common/      → Shared constants (CATEGORY_MAP)
```

## Daily Update Pipeline

```bash
# Run full pipeline for a specific date (Always BUILD before bulk runs to ensure logic sync)
docker compose build processor importer calculator
./scripts/daily_update.sh 20260201

# Manual steps (Use --rm for transient tasks):
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor python convert_institutional_summary.py
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer
START_DATE=20260201 END_DATE=20260201 docker compose run --rm calculator
```

Pipeline order matters: scraper → processor → importer → calculator.

## Known Data Gaps & Market Rules

### OTC Index Holidays (Trading Closed)
The following dates correctly return no data for OTC indices due to market closures:
- **2022-02-04**: Lunar New Year Holiday
- **2023-01-18**: Market Closing Day (Last trading day before Lunar New Year)
- **2024-10-31**: Typhoon Kong-rey
- **Weekends/National Holidays**: No data for any market category.

### Unified Processing Logic
- `processor/convert.py` is the **single entry point**.
- It checks for specific output files (`otc.csv`, `sii.csv`, `all.csv`) in the processed directory to determine if a date/category is truly "complete", allowing for granular backfilling.

## Data Sources & Update Frequency

| Source | Service | What it fetches | Update Frequency |
|--------|---------|----------------|------------------|
| TWSE (twse.com.tw) | `scraper-daily` | Daily quotes, institutional investors, foreign holdings, margin, P/E, indices | Daily (after market close) |
| TPEx (tpex.org.tw) | `scraper-daily` | Same categories for OTC-listed stocks + Index Summary | Daily (after market close) |
| MOPS (mopsov.twse.com.tw) | `scraper-monthly` | Monthly revenue reports | Monthly (before 10th) |
| MOPS (mopsov.twse.com.tw) | `scraper-quarterly` | Quarterly financial reports (SII/OTC), income statement (t163sb04), balance sheet (t163sb05), cash flow (t163sb20) | Quarterly (approx. 45 days after Q-end) |
| TDCC (tdcc.com.tw) | `scraper-weekly` | Shareholding dispersion per stock | Weekly (scraped on Sunday) |

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

All pipeline services use these:

| Variable | Default | Description |
|----------|---------|-------------|
| `START_DATE` | today | YYYYMMDD format |
| `END_DATE` | today | YYYYMMDD format |
| `MARKET_TYPE` | ALL | SII, OTC, or ALL |
| `FETCH_DELAY` | 3.0 | Seconds between scraper requests |
| `FORCE_REPROCESS` | 0 | Set to 1 to reprocess already-processed files (processor) |
| `FORCE_REIMPORT` | 0 | Set to 1 to overwrite existing DB data (importer) |
| `IMPORT_CATEGORY` | (all) | Import only a specific category |
| `REVENUE_YEAR` | - | For scraper-monthly (AD year) |
| `REVENUE_MONTH` | - | For scraper-monthly |
| `TDCC_DATE` | - | For scraper-weekly (YYYYMMDD) |

Database (shared with backend):

| Variable | Default |
|----------|---------|
| `DB_HOST` | db |
| `DB_USER` | user |
| `DB_PASSWORD` | password |
| `DB_NAME` | stock_db |
| `DB_PORT` | 5432 |

## Processor Modules

| Module | Purpose |
|--------|---------|
| `convert.py` | **Unified ETL entry point**: Auto-dispatches to correct handler based on category. Handles stocks, summaries, and indices. |
| `convert_quarterly_reports.py` | Specifically handles SII/OTC quarterly reports (Excel parsing). |
| `validator.py` | Validates row counts and numeric accuracy (Raw vs Processed) |
| `data_quality_checker.py` | Post-ETL verification script to catch NULL values or missing files. **Writes findings to root `error.md`**. |
| `schemas.py` | Column mappings, numeric types, standard schema definitions. |
| `utils.py` | Shared helpers: **Header merging for multi-line CSVs**, index extraction. |

### Advanced Processing Features (convert.py)

1. **Unified Pipeline**: All categories (OHLCV, Institutional, Margin, etc.) are processed via `python convert.py`.
2. **Incremental Processing**: By default, skips files that already exist in the processed directory. Set `FORCE_REPROCESS=1` to force reprocessing.
3. **Multi-line Header Merging**: `utils.read_raw_csv` automatically detects and merges category-subheader rows (common in TWSE/TPEx CSVs).
4. **Quarterly Report Parsing (SII)**: Handles complex multi-row headers (Rows 2-5) in 2025+ SII Excel files by locating the first row with a 4-digit numeric symbol and using fixed index-based mapping (Col 13: EPS, Col 20: Op Cash Flow).
5. **Reference Category (ref_cat) Fallback**: Virtual categories (e.g., `margin_summary`) automatically scan the date directories of their source categories (e.g., `margin_trading`) to ensure processing even if the target raw directory is missing.
6. **Market Index Extraction**:
   - **SII**: Extracted from `daily_quotes/sii.csv` via `utils.read_sii_indices`.
   - **OTC**: Fetched as a dedicated category using modernized TPEx JSON-to-CSV APIs.

Run validation after processing:
```bash
docker compose run --rm processor python validator.py
```

## Processor Column Mapping

The processor converts Chinese column names to English. Key mappings in `processor/schemas.py`:

- 證券代號 → symbol
- 成交股數 → volume
- 開盤價 → open / 收盤價 → close / 最高價 → high / 最低價 → low
- 外陸資買賣超股數 → foreign_net
- 投信買賣超股數 → trust_net

## Calculator: Technical Indicators

Computed for every stock, stored in `technical_indicators` table.
Uses Pandas vectorized operations with grouped apply (by symbol) for efficiency.

- **MA**: 5, 10, 20, 60, 120, 240-day moving averages
- **VMA**: Volume moving averages (same periods)
- **KD**: Stochastic oscillator (9-period RSV, smoothing α=1/3)
- **RSI**: 6-period and 12-period
- **MACD**: DIF (EMA12-EMA26), DEA (EMA9 of DIF), histogram
- **Bollinger Bands**: MA20 ± 2σ

## Important Pipeline Behaviors

1. **Incremental by default**: Each stage skips existing data. Use `FORCE_REIMPORT=1` for importer to delete and re-import (Delete-before-Insert).
2. **Encoding**: Raw CSVs from TWSE/TPEx are Big5 → converted to UTF-8-sig by scraper.
3. **ETF & preferred stock filtering**: Importer excludes symbols starting with "00" (ETFs) and symbols containing letters (preferred stocks like 1101B).
4. **OHLCV validation**: Importer filters rows where all of open/high/low/close/volume are NULL or 0.
5. **Rate limiting**: Scraper waits 3 seconds between requests. TDCC uses random 1-2s delays.
6. **Taiwan calendar**: Uses `pandas_market_calendars` (XTAI) to determine trading days.
7. **ROC year**: MOPS uses 民國 year (AD year - 1911). Scraper handles conversion.
8. **Database wait**: Importer has built-in retry logic to wait for database availability.
9. **market_indices extraction**: Processor auto-extracts market indices from daily_quotes during conversion.

## Common Data Pipeline Tasks

### Batch import historical data
```bash
# Process + import a full year (uses unified convert.py)
for date in $(python3 -c "
import pandas_market_calendars as mcal
cal = mcal.get_calendar('XTAI')
for d in cal.schedule('2022-01-01','2022-12-31').index:
    print(d.strftime('%Y%m%d'))
"); do
  START_DATE=$date END_DATE=$date docker compose run --rm processor
  START_DATE=$date END_DATE=$date docker compose run --rm importer
done
# Then recalculate all indicators
docker compose run --rm calculator
```

### Force recalculate all technical indicators
```bash
docker compose run --rm calculator
```

### Import only one category
```bash
docker compose run --rm -e IMPORT_CATEGORY=monthly_revenue importer
```

Available `IMPORT_CATEGORY` values:
- `daily_quotes` — Daily OHLCV data
- `market_indices` — Market indices (auto-extracted from daily_quotes)
- `institutional_investors` — Institutional buy/sell per stock
- `institutional_summary` — Institutional buy/sell market-level summary
- `foreign_holding` — Foreign shareholding ratio
- `margin_trading` — Margin long/short balance
- `margin_sbl` — Securities borrowing and lending
- `margin_summary` — Market-level margin trading summary
- `pe_ratio` — Price-to-earnings ratio
- `monthly_revenue` — Monthly revenue
- `shareholding_div` — TDCC shareholding dispersion

### Force re-import (delete and re-import existing data)
```bash
docker compose run --rm -e FORCE_REIMPORT=1 -e IMPORT_CATEGORY=shareholding_div importer
```
Note: `FORCE_REIMPORT` must be passed via `-e` flag, not as a shell env var prefix.

### Process shareholding_div2 (historical all-in-one TDCC format)
```bash
docker compose run --rm processor python convert_shareholding2.py
# Or with date range:
START_DATE=20200103 END_DATE=20230908 docker compose run --rm processor python convert_shareholding2.py
```
Both `convert_shareholding.py` and `convert_shareholding2.py` output to the same `data/processed/shareholding_div/` directory.

### TDCC manual steps (if not using Docker)
```bash
# Step 1: Generate active stock list from latest monthly revenue
python scraper/generate_active_stocks.py  # outputs active_stocks.txt

# Step 2: Query available dates from TDCC
python scraper/fetch_tdcc_history.py --list-dates

# Step 3: Fetch data for specific date
python scraper/fetch_tdcc_history.py -f active_stocks.txt -d 20250321
```

### Monthly revenue manual fetch
```bash
# Fetch a specific month (e.g. 2026/01)
REVENUE_YEAR=2026 REVENUE_MONTH=1 docker compose run --rm scraper-monthly
# Then process + import
START_DATE=20260101 END_DATE=20260101 docker compose run --rm processor python convert_monthly_revenue.py
docker compose run --rm -e START_DATE=20260101 -e END_DATE=20260101 -e IMPORT_CATEGORY=monthly_revenue importer
```
Note: Monthly revenue is published before the 10th of each month. Fetching after the 11th ensures completeness.

### Quarterly report manual fetch
```bash
# Fetch 2025 Q3
REPORT_YEAR=2025 REPORT_QUARTER=3 docker compose run --rm scraper-quarterly
# Process + Import (Use YYYYQX for start/end date for quarterly reports)
START_DATE=2025Q3 END_DATE=2025Q3 docker compose run --rm processor python convert_quarterly_reports.py
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 -e IMPORT_CATEGORY=quarterly_reports importer
```

### Automation schedules (launchctl)

| Schedule | Plist | Script | Time |
|----------|-------|--------|------|
| Daily quotes | `com.poyilee.stock-daily-update` | StockDailyUpdate.app | Every day 21:00 |
| Weekly TDCC | `com.poyilee.stock-weekly-update` | `scripts/weekly_tdcc_update.sh` | Every Sunday 13:15 |
| Monthly revenue | `com.poyilee.stock-monthly-update` | `scripts/monthly_revenue_update.sh` | Every 12th 17:00 |

**Note on Daily Schedule Timing (21:00):**
- TWSE publishes most data immediately after market close (~14:30)
- **Foreign holding data (`foreign_holding`) is published with delay** - typically available after 20:00
- Daily schedule set to 21:00 ensures all data (including foreign_holding) is available
- If scraper runs too early, foreign_holding files will only contain headers (no data rows)

All plist files are in `~/Library/LaunchAgents/`. Manage with:
```bash
launchctl load ~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist
launchctl unload ~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist
launchctl list | grep poyilee  # verify loaded
```

TDCC scraper features:
- Auto CSRF token management (parses and renews session tokens)
- Checkpoint resume (skips existing .csv files, safe to re-run on failure)
- `--no-verify` flag for SSL certificate issues

## Docker Services Reference

| Service | Command | Purpose |
|---------|---------|---------|
| `scraper-daily` | `python main.py` | Fetch daily market data |
| `scraper-weekly` | `python fetch_tdcc_history.py -f ... -d $TDCC_DATE` | Fetch TDCC shareholding (fixed command, requires TDCC_DATE) |
| `scraper-monthly` | `python fetch_monthly_revenue.py --year $REVENUE_YEAR --month $REVENUE_MONTH` | Fetch monthly revenue (requires REVENUE_YEAR, REVENUE_MONTH) |
| `processor` | `python convert.py` | Process daily data |
| `importer` | `python main.py` | Load CSVs into PostgreSQL |
| `calculator` | `python main.py` | Compute technical indicators |
| `db` | postgres:15 | PostgreSQL database |
| `backend` | uvicorn | FastAPI server (port 8000) |
| `frontend` | next start | Next.js UI (port 3000) |
