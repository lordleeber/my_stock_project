# Importer Module Guide (for AI Assistants)

This guide covers the database import component of the Taiwan stock market analysis pipeline.

## Overview

The importer loads processed CSV data into PostgreSQL database:
- Recalculates lineage columns (`src_file`, `src_row`, `src_col` → `pced_file`, `pced_row`, `pced_col`) to point to processed CSV positions
- Validates and filters data before import (ETF/preferred stocks, OHLCV validation)
- Preserves lineage metadata in database for traceability
- Performs per-date lineage-based validation after import
- Uses delete-before-insert strategy for data updates
- Supports incremental and full refresh modes
- Handles deduplication by date+market or date+symbol
- **Fail-fast**: any import error writes to `error_importer.md` and exits immediately (`SystemExit(1)`)

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
| `ENABLE_FULL_DIFF` | 0 | Set to 1 to enable detailed row-by-row validation (slower) |
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
docker compose run --rm -e FORCE_REIMPORT=1 -e IMPORT_CATEGORY=shareholding importer
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
| `shareholding` | `shareholding` | TDCC shareholding dispersion |
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

### 4. Lineage Tracking (Data Traceability)
The processor adds `src_file`, `src_row`, `src_col` columns to processed CSVs pointing to raw data sources. The importer **recalculates** these columns to point to processed CSV positions before storing them in the database as `pced_file`, `pced_row`, `pced_col`.

**Lineage Calculation (in `recalculate_lineage()`):**
- Executed **BEFORE** ETF/OHLCV filtering to record original CSV positions
- **pced_file**: Path to the processed CSV file (e.g., `/app/data/processed/foreign_holding/2020/20200102/sii.csv`)
- **pced_row**: 1-based line number in processed CSV (row 1 = header, row 2 = first data row)
- **pced_col**: Column position mapping (format: `1#2#3#4#...` for each column)

**Why recalculate?**
- Processor's `src_*` points to raw CSV (for QC purposes)
- Importer reads from processed CSV, so lineage should reflect the actual import source
- Enables accurate validation by comparing DB data against processed CSV at exact positions

**Validation Usage:**
- Reads processed CSV without filtering
- Uses `pced_row` to locate exact row in original CSV
- Performs column-by-column value comparison
- Reports any discrepancies (type-aware: int/float/string)

### 5. Row Count Verification
After each `to_sql()` call (except `stock_info`/`stock_tags` which use `replace` mode), the importer runs `verify_row_count()` to compare the number of rows just imported against `SELECT COUNT(*) FROM table WHERE date = ...`. Mismatches are logged with `❌ Row count mismatch`.

### 6. Fail-Fast Error Handling
Any import error immediately writes the error and traceback to `/app/error_importer.md` and exits with `SystemExit(1)`. The importer does **not** silently skip failed imports.

### 7. Database Wait Logic
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
docker compose run --rm -e FORCE_REIMPORT=1 -e IMPORT_CATEGORY=shareholding importer
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

## Validation System

Importer automatically validates imported data to ensure database content matches CSV files.

### Lineage-Based Validation (Per-Date, Always Enabled)

After importing each date, the importer performs **lineage-based validation** using the `pced_*` columns stored in the database:

**How it works:**
1. Queries all rows for the imported date from database (includes `pced_file`, `pced_row`, `pced_col`)
2. Groups by `pced_file` to minimize file I/O
3. For each file:
   - Reads the processed CSV **without filtering** (preserves original row positions)
   - For each DB row:
     - Locates the source row using `pced_row` (CSV row index = `pced_row - 2`, since row 1 = header)
     - Compares column values with type-aware logic:
       - **Integers** (volume, shares): Exact match after float→int conversion
       - **Floats** (prices, ratios): Tolerance-based (0.0001 for prices, 0.01% for percentages)
       - **Strings** (symbol, name): Exact match after trimming whitespace
     - Reports any mismatches

**Output**: Immediate failure on first error with details in `error_importer.md`

**Benefits:**
- ✅ **Column-level accuracy**: Verifies every field, not just aggregates
- ✅ **Early detection**: Catches import bugs before data corruption spreads
- ✅ **Full traceability**: Know exactly which CSV row produced each DB record
- ✅ **Fast**: Only reads relevant CSV files for the imported date

**Example output:**
```
→ foreign_holding 2020-01-02: 驗證 1685 rows with lineage...
✓ foreign_holding 2020-01-02: 1685 rows verified from 2 files
```

### Additional Validation Levels (Optional)

#### 1. Statistical Validation (Legacy, for Full Date Range)
Fast validation comparing aggregate statistics across all imported dates:
- Row counts, unique dates/symbols
- Sum/average of numeric fields (volume, value, PE ratio, etc.)
- Allows 0.01% floating-point tolerance

**Output**: `error_importer.md` (only created if validation fails)

**Time**: 1-2 minutes

**Note**: With lineage-based validation enabled per-date, statistical validation is primarily useful for verifying entire date ranges after bulk imports.

#### 2. Full Diff Validation (Deep Analysis)
Detailed row-by-row comparison:
- Exports entire DB table to DataFrame
- Loads all CSVs and merges
- Identifies records only in CSV, only in DB, or with value differences
- Samples up to 10,000 rows for value comparison

**Output**: `error_importer_diff.md`

**Time**: 5-10 minutes (memory intensive)

**Enable with**: `ENABLE_FULL_DIFF=1`

### Usage Examples

```bash
# Normal import with automatic statistical validation
START_DATE=20200210 END_DATE=20200210 docker compose run --rm importer

# Enable full diff for detailed analysis
START_DATE=20200210 END_DATE=20200210 ENABLE_FULL_DIFF=1 docker compose run --rm importer

# Full diff for specific table only
IMPORT_CATEGORY=daily_quotes ENABLE_FULL_DIFF=1 docker compose run --rm importer
```

### Interpreting Validation Reports

#### error_importer.md (Statistical Report)
```
### daily_quotes
- total_rows: CSV=3075602, DB=2666920
- sum_volume: CSV=2009784413610.00, DB=1876122350426.00, 差異=6.6506%
```

**What to check**:
- Row count differences > 10% → investigate
- Numeric differences > 1% → investigate
- Small differences (< 0.1%) → likely rounding/filtering, acceptable

#### error_importer_diff.md (Detailed Report)
```
### 只在 CSV 存在（461,900 筆）
2022-09-13|00865B  ← ETF filtered by importer
2023-04-24|00700   ← ETF filtered by importer
2022-07-29|9941A   ← Preferred stock filtered by importer

### 只在 DB 存在（53,216 筆）
2026-01-02|2611    ← Data outside date range
2026-01-23|1310    ← Old data not in current CSV

### 數值差異
**2020-01-02|020000**
- `volume`: CSV=`284000.0` vs DB=`284000`  ← Format difference (normal)
```

**What each section means**:
- **Only in CSV**: Usually ETFs (00xxx) or preferred stocks (xxxA/B) filtered by importer → **Normal**
- **Only in DB**: Records outside START_DATE/END_DATE range → **Normal** (unless using FORCE_REIMPORT)
- **Value differences**: Check if format differences (`.0` suffix) or real data errors

### Common Validation Scenarios

#### Scenario 1: Large row count difference, mostly ETFs
**Symptom**: CSV has 400k more rows, diff shows 00xxxx symbols

**Cause**: ETF filtering is working as designed

**Action**: No action needed

#### Scenario 2: Recent dates only in DB
**Symptom**: DB has 2026-02-xx records not in CSV

**Cause**: CSV filtered by START_DATE/END_DATE, but DB has historical data

**Action**: No action unless you want to clean old data with FORCE_REIMPORT

#### Scenario 3: Many value differences with `.0` suffix
**Symptom**: CSV=`123.0` vs DB=`123` for thousands of rows

**Cause**: String representation of float vs numeric

**Action**: No action (both values are equal)

#### Scenario 4: Real numeric differences > 1%
**Symptom**: sum_volume differs by 10%

**Cause**: Processor error, importer bug, or corrupted data

**Action**:
1. Check processor logs
2. Verify raw CSV files
3. Use `FORCE_REIMPORT=1` to re-import
4. If persists, investigate data source

### When to Use Full Diff

- Statistical validation shows large differences (> 1%)
- Suspect data quality issues
- After major processor changes
- Debugging specific table problems
- **Don't use** for routine imports (too slow)

### Implementation Details

**Files**:
- `validator.py`: Statistical validation logic
- `full_diff.py`: Detailed comparison logic
- `main.py`: Orchestrates validation after import

**Key Functions**:
```python
# Statistical validation
from validator import validate_all_tables
all_passed, all_errors = validate_all_tables(engine)

# Full diff validation
from full_diff import full_diff_validation, write_diff_report
diff_reports = full_diff_validation(engine)
write_diff_report(diff_reports, "/app/error_importer_diff.md")
```

**Validation runs automatically** - no need to manually invoke unless debugging.

## Next Steps

After importing, data flows to:
- **Calculator** (`calculator/CLAUDE.md`) - Computes technical indicators
- **Backend API** (`backend/CLAUDE.md`) - Serves data to frontend
