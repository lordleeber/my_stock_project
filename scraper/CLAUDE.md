# Data Pipeline Guide (for AI Assistants)

This document covers the **entire data pipeline**: scraper → processor → importer → calculator.
All components live in the project root under their respective directories.

## Maintaining This Document

**After completing each task**, review this CLAUDE.md to ensure it remains consistent with the actual code. If you modified any behavior, schema, environment variable, or pipeline logic, update the relevant sections here. Keeping this document in sync with the codebase is essential for future AI assistants.

## Architecture Overview

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
# Run full pipeline for a specific date
./scripts/daily_update.sh 20260201

# Or run each step manually via Docker
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor python convert_institutional_summary.py
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer
START_DATE=20260201 END_DATE=20260201 docker compose run --rm calculator
```

Pipeline order matters: scraper → processor → importer → calculator.

## Data Sources & Update Frequency

| Source | Service | What it fetches | Update Frequency |
|--------|---------|----------------|------------------|
| TWSE (twse.com.tw) | `scraper-daily` | Daily quotes, institutional investors, foreign holdings, margin, P/E | Daily (after market close) |
| TPEx (tpex.org.tw) | `scraper-daily` | Same categories for OTC-listed stocks | Daily (after market close) |
| MOPS (mopsov.twse.com.tw) | `scraper-monthly` | Monthly revenue reports | Monthly (before 10th) |
| TDCC (tdcc.com.tw) | `scraper-weekly` | Shareholding dispersion per stock | Weekly (Friday after close) |

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
│   └── shareholding_div/date=YYYYMMDD/{symbol}.csv
├── processed/                    # Processor output (cleaned CSVs)
│   └── (same structure, standardized schemas)
└── postgres/                     # PostgreSQL data volume
```

## Environment Variables

All services use these:

| Variable | Default | Description |
|----------|---------|-------------|
| `START_DATE` | today | YYYYMMDD format |
| `END_DATE` | today | YYYYMMDD format |
| `MARKET_TYPE` | ALL | SII, OTC, or ALL |
| `FETCH_DELAY` | 3.0 | Seconds between scraper requests |
| `FORCE_REIMPORT` | 0 | Set to 1 to overwrite existing DB data |
| `IMPORT_CATEGORY` | (all) | Import only a specific category |
| `REVENUE_YEAR` | - | For scraper-monthly (AD year) |
| `REVENUE_MONTH` | - | For scraper-monthly |
| `TDCC_DATE` | - | For scraper-weekly (YYYYMMDD) |

Database (used by importer, calculator, backend):

| Variable | Default |
|----------|---------|
| `DB_HOST` | db |
| `DB_USER` | user |
| `DB_PASSWORD` | password |
| `DB_NAME` | stock_db |
| `DB_PORT` | 5432 |

## Key Database Tables

| Table | Key columns | Source |
|-------|------------|--------|
| `daily_quotes` | date, symbol, open, high, low, close, volume | TWSE/TPEx daily |
| `technical_indicators` | date, symbol, ma5..ma240, k, d, rsi6, rsi12, macd_dif, macd_dea | Calculated |
| `institutional_investors` | date, symbol, foreign_net, trust_net, dealer_net | TWSE/TPEx T86 |
| `foreign_holding` | date, symbol, foreign_held_shares, foreign_held_ratio | TWSE/TPEx QFIIS |
| `margin_trading` | date, symbol, margin_long_balance, margin_short_balance | TWSE/TPEx |
| `monthly_revenue` | date, symbol, revenue, yoy_pct | MOPS |
| `shareholding_div` | date, symbol, level, holders, shares | TDCC |
| `market_indices` | date, symbol, close, change | Extracted from daily_quotes |

## Processor Modules

| Module | Purpose |
|--------|---------|
| `convert.py` | Main ETL for daily data; auto-extracts `market_indices` from `daily_quotes` |
| `convert_monthly_revenue.py` | Monthly revenue ETL (handles MOPS format variations) |
| `convert_shareholding.py` | Merges per-stock TDCC CSVs into single file per date |
| `convert_institutional_summary.py` | Standardizes SII/OTC institution names and merges |
| `validator.py` | Validates row counts and numeric accuracy (Raw vs Processed) |
| `schemas.py` | Column mappings, numeric types, standard schema definitions |
| `utils.py` | Shared helpers: header detection, index extraction |

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

## Important Behaviors

1. **Incremental by default**: Each stage skips existing data. Use `FORCE_REIMPORT=1` for importer to delete and re-import (Delete-before-Insert).
2. **Encoding**: Raw CSVs from TWSE/TPEx are Big5 → converted to UTF-8-sig by scraper.
3. **ETF filtering**: Importer excludes symbols starting with "00" (ETFs).
4. **OHLCV validation**: Importer filters rows where all of open/high/low/close/volume are NULL or 0.
5. **Rate limiting**: Scraper waits 3 seconds between requests. TDCC uses random 1-2s delays.
6. **Taiwan calendar**: Uses `pandas_market_calendars` (XTAI) to determine trading days.
7. **ROC year**: MOPS uses 民國 year (AD year - 1911). Scraper handles conversion.
8. **Database wait**: Importer has built-in retry logic to wait for database availability.
9. **market_indices extraction**: Processor auto-extracts market indices from daily_quotes during conversion.

## Common Tasks

### Batch import historical data
```bash
# Process + import a full year
for date in $(python3 -c "
import pandas_market_calendars as mcal
cal = mcal.get_calendar('XTAI')
for d in cal.schedule('2022-01-01','2022-12-31').index:
    print(d.strftime('%Y%m%d'))
"); do
  START_DATE=$date END_DATE=$date docker compose run --rm processor
  START_DATE=$date END_DATE=$date docker compose run --rm processor python convert_institutional_summary.py
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
- `pe_ratio` — Price-to-earnings ratio
- `monthly_revenue` — Monthly revenue
- `shareholding_div` — TDCC shareholding dispersion

### TDCC manual steps (if not using Docker)
```bash
# Step 1: Generate active stock list from latest monthly revenue
python scraper/generate_active_stocks.py  # outputs active_stocks.txt

# Step 2: Query available dates from TDCC
python scraper/fetch_tdcc_history.py --list-dates

# Step 3: Fetch data for specific date
python scraper/fetch_tdcc_history.py -f active_stocks.txt -d 20250321
```

TDCC scraper features:
- Auto CSRF token management (parses and renews session tokens)
- Checkpoint resume (skips existing .csv files, safe to re-run on failure)
- `--no-verify` flag for SSL certificate issues

## Docker Services Reference

| Service | Command | Purpose |
|---------|---------|---------|
| `scraper-daily` | `python main.py` | Fetch daily market data |
| `scraper-weekly` | `python fetch_tdcc_history.py` | Fetch TDCC shareholding |
| `scraper-monthly` | `python fetch_monthly_revenue.py` | Fetch monthly revenue |
| `processor` | `python convert.py` | Process daily data |
| `importer` | `python main.py` | Load CSVs into PostgreSQL |
| `calculator` | `python main.py` | Compute technical indicators |
| `db` | postgres:15 | PostgreSQL database |
| `backend` | uvicorn | FastAPI server (port 8000) |
| `frontend` | next start | Next.js UI (port 3000) |
