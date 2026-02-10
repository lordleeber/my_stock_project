# Importer Module Guide (for AI Assistants)

This guide covers the database import component of the Taiwan stock market analysis pipeline.

## Overview

The importer loads processed CSV data into PostgreSQL database:
- Validates and filters data before import
- Uses delete-before-insert strategy for data updates
- Supports incremental and full refresh modes
- Handles deduplication by date+market or date+symbol

**Input**: `data/processed/` (from processor)
**Output**: PostgreSQL tables in `stock_db`

## Database Connection

```python
def get_db_url():
    # Env vars: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
    # Defaults: user, password, db, 5432, stock_db
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
```

Uses SQLAlchemy engine with psycopg2 driver.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `START_DATE` | - | YYYYMMDD format (or YYYYQX for quarterly reports) |
| `END_DATE` | - | YYYYMMDD format (or YYYYQX for quarterly reports) |
| `IMPORT_CATEGORY` | (all) | Import only a specific category |
| `FORCE_REIMPORT` | 0 | Set to 1 to delete and re-import existing data |
| `DB_HOST` | db | PostgreSQL host |
| `DB_USER` | user | Database user |
| `DB_PASSWORD` | password | Database password |
| `DB_NAME` | stock_db | Database name |
| `DB_PORT` | 5432 | Database port |

## Docker Service

```bash
# Import all categories for a specific date
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer

# Import only one category
docker compose run --rm -e IMPORT_CATEGORY=monthly_revenue importer

# Force re-import (delete and re-import existing data)
docker compose run --rm -e FORCE_REIMPORT=1 -e IMPORT_CATEGORY=shareholding_div importer
```

**Important Notes**:
- `FORCE_REIMPORT` must be passed via `-e` flag, not as a shell env var prefix
- Always rebuild after code changes: `docker compose build importer`

## Import Categories

Available `IMPORT_CATEGORY` values:

| Category | Table | Description |
|----------|-------|-------------|
| `daily_quotes` | `daily_quotes` | Daily OHLCV data |
| `market_indices` | `market_indices` | Market indices (auto-extracted from daily_quotes) |
| `institutional_investors` | `institutional_investors` | Institutional buy/sell per stock |
| `institutional_summary` | `institutional_summary` | Institutional buy/sell market-level summary |
| `foreign_holding` | `foreign_holding` | Foreign shareholding ratio |
| `margin_trading` | `margin_trading` | Margin long/short balance |
| `margin_sbl` | `margin_sbl` | Securities borrowing and lending |
| `margin_summary` | `margin_summary` | Market-level margin trading summary |
| `pe_ratio` | `pe_ratio` | Price-to-earnings ratio |
| `monthly_revenue` | `monthly_revenue` | Monthly revenue |
| `shareholding_div` | `shareholding_div` | TDCC shareholding dispersion |
| `quarterly_reports` | `quarterly_reports` | Quarterly financial summary |
| `income_statements` | `income_statements` | Quarterly income statements |
| `balance_sheets` | `balance_sheets` | Quarterly balance sheets |
| `cash_flows` | `cash_flows` | Quarterly cash flow statements |

## Import Behaviors

### 1. Incremental by Default
Each import skips data that already exists in the database. Use `FORCE_REIMPORT=1` to delete and re-import.

### 2. Delete-Before-Insert Strategy
When `FORCE_REIMPORT=1` or updating existing data:
- Deletes rows matching `date` (and `market` or `symbol`) before inserting new data
- Prevents duplicate entries
- Ensures data consistency

### 3. Data Filtering

#### ETF & Preferred Stock Filtering
Importer excludes:
- **ETFs**: Symbols starting with "00" (e.g., 0050, 0056)
- **Preferred stocks**: Symbols containing letters (e.g., 1101B, 2330A)

Only ordinary common stocks are imported.

#### OHLCV Validation
Filters rows where all of the following are NULL or 0:
- open
- high
- low
- close
- volume

This removes invalid trading day records.

### 4. Database Wait Logic
Importer has built-in retry logic (up to 30 seconds) to wait for database availability. This is useful when starting services with `docker compose up`.

## Common Import Tasks

### Import Historical Data for a Year
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
```

### Import Monthly Revenue
```bash
# After scraping and processing
docker compose run --rm -e START_DATE=20260101 -e END_DATE=20260101 -e IMPORT_CATEGORY=monthly_revenue importer
```

### Import Quarterly Reports
```bash
# Use YYYYQX format for quarterly reports
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 -e IMPORT_CATEGORY=quarterly_reports importer
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 -e IMPORT_CATEGORY=income_statements importer
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 -e IMPORT_CATEGORY=balance_sheets importer
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 -e IMPORT_CATEGORY=cash_flows importer
```

### Force Reimport TDCC Data
```bash
# Delete existing data and reimport
docker compose run --rm -e FORCE_REIMPORT=1 -e IMPORT_CATEGORY=shareholding_div importer
```

## Database Schema Notes

### Date Column Types
All `date` columns use **TEXT** type (not DATE), storing values as:
- Daily data: "YYYY-MM-DD" (e.g., "2026-02-01")
- Quarterly data: "YYYYQX" (e.g., "2025Q3")

### Symbol Column Types
All `symbol` columns use **TEXT** type (standardized across 10 tables).

### Bid/Ask in daily_quotes
`bid` and `ask` fields are **TEXT** type in the database (preserved from source format).

## Indexes

After importing data, ensure critical indexes exist for optimal query performance:

```bash
# Verify indexes
docker compose exec -T db psql -U user -d stock_db -c \
  "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'idx_%' ORDER BY tablename, indexname;"

# Recreate missing indexes (from backend service)
docker compose run --rm backend python create_indexes.py
```

**Expected indexes (5 total)**:
- `idx_daily_quotes_date_symbol` (daily_quotes)
- `idx_daily_quotes_symbol_date` (daily_quotes)
- `idx_tech_symbol_date` (technical_indicators)
- `idx_institutional_investors_symbol_date` (institutional_investors)
- `idx_foreign_holding_symbol_date` (foreign_holding)

## Troubleshooting

### Issue: Import fails with "database does not exist"
- **Solution**: Wait for database to start. Importer has built-in retry logic (30s), but if it still fails, check if `db` service is running: `docker compose ps db`

### Issue: Duplicate key violations
- **Solution**: Use `FORCE_REIMPORT=1` to delete existing data before import

### Issue: No data imported even though processed files exist
- **Solution**: Check if data already exists in database. Importer skips existing data by default. Use `FORCE_REIMPORT=1` to override.

### Issue: Import succeeds but backend API returns no data
- **Solution**: Verify indexes exist (see Indexes section above). Missing indexes can cause query failures.

### Issue: ETF data (0050, 0056) not in database
- **Expected behavior**: ETFs are intentionally filtered out. Importer only imports ordinary common stocks.

## Next Steps

After importing, data flows to:
- **Calculator** (`calculator/CLAUDE.md`) - Computes technical indicators
- **Backend API** (`backend/CLAUDE.md`) - Serves data to frontend
