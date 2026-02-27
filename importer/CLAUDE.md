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
- **Fail-fast**: any import error writes to `error_importer.log` and exits immediately (`SystemExit(1)`)

### 🔴 STRICT IMAGE REBUILD RULE (CORE MANDATE)

`importer` does not mount source code into `/app`. After any code change in `importer/`, you **MUST** rebuild before running:

```bash
docker compose build importer
```

If you skip rebuild, container runtime may execute stale code even when host files look updated.

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
| `FORCE_REIMPORT` | 0 | Set to 1 to delete and re-import existing data |
| `DB_HOST` | db | PostgreSQL host |
| `DB_USER` | user | Database user |
| `DB_PASSWORD` | password | Database password |
| `DB_NAME` | stock_db | Database name |
| `DB_PORT` | 5432 | Database port |

## Docker Service

```bash
# Daily import for a specific date
docker compose run --rm -e START_DATE=20260201 -e END_DATE=20260201 importer python import_daily.py

# Weekly import (shareholding)
docker compose run --rm -e START_DATE=20260207 -e END_DATE=20260207 importer python import_weekly.py

# Monthly import
docker compose run --rm -e START_DATE=20260101 -e END_DATE=20260101 importer python import_monthly.py

# Quarterly import
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 importer python import_quarterly.py

# Quarterly XBRL import
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 importer python import_quarterly_xbrl.py
```

**Important Notes**:
- `FORCE_REIMPORT` must be passed via `-e` flag, not as a shell env var prefix
- Always rebuild after code changes: `docker compose build importer`

## Import Entry Points

| Entry | Scope | Description |
|----------|-------|-------------|
| `import_daily.py` | Daily categories | daily_quotes, market_indices, institutional_investors, institutional_summary, foreign_holding, margin_trading, margin_sbl, margin_summary, pe_ratio |
| `import_weekly.py` | Weekly categories | shareholding |
| `import_monthly.py` | Monthly categories | monthly_revenue, stock_info, stock_tags |
| `import_quarterly.py` | Quarterly categories | quarterly_reports, income_statement, balance_sheet, cash_flow |
| `import_quarterly_xbrl.py` | Quarterly XBRL categories | balance_sheet_xbrl, income_statement_xbrl, cash_flow_xbrl |

`import_daily.py` runs all daily categories in sequence for the date range.  
For long ranges (for example a full year), runtime can be very long; this is expected and not a hang.

## Import Behaviors

### 1. Incremental by Default
Each import skips data that already exists in the database. Use `FORCE_REIMPORT=1` to delete and re-import.

### 2. Delete-Before-Insert Strategy
When `FORCE_REIMPORT=1` or updating existing data:
- Deletes rows matching `date` (and `market` or `symbol`) before inserting new data
- Prevents duplicate entries
- Ensures data consistency

### 3. Data Filtering

#### Strict Stock Filtering
Importer strictly only allows **4-digit numeric symbols** (e.g., "2330", "2317"). 
- Filters out all other symbols including ETFs ("00xxxx"), preferred stocks ("xxxxA/B"), warrants, and REITs.
- This ensures only ordinary common stocks are stored in the primary database tables.

#### Symbol Whitespace Normalization (shareholding)
For weekly `shareholding` imports, `symbol` is trimmed before filtering and insert.
This prevents right-padded symbols like `2330  ` from being stored in DB.

#### OHLCV Validation
Filters rows where all of the following are NULL or 0:
- open
- high
- low
- close
- volume

This removes invalid trading day records from the `daily_quotes` table.

### 4. Lineage Tracking (Data Traceability)
The processor adds `pced_file`, `pced_row`, `pced_col` columns to processed CSVs. The importer preserves these metadata columns in the database for full traceability.

**Lineage-Based Validation:**
- After each import, the system compares database records against the processed CSV at the exact `pced_row` positions.
- Uses **explicit schemas** from `common/schemas.py` to ensure type-safe comparisons.

### 5. Schema Enforcement (No Inference)
The importer **no longer relies on automatic type inference**. It uses `common/schemas.py` as a single source of truth:
- Every `pl.read_csv` call uses `schema_overrides` from the shared schema.
- This prevents numeric symbols from being incorrectly detected as integers (bigint).
- **Dual-Column Support**: For flow statements (`income_statement`, `cash_flow`, `quarterly_reports`), the importer correctly handles both single-quarter (`_q`) and accumulated (`_acc`) fields as defined in the schema.
- **XBRL Wide-to-Long Import**: Quarterly XBRL exports are converted from wide `codeN/valueN` CSV into row-based records before DB import:
  - `balance_sheet_xbrl`: reads `all.csv` (period type `as_of`)
  - `income_statement_xbrl`: reads `all_quarter.csv` + `all_accumulated.csv`
  - `cash_flow_xbrl`: reads `all_accumulated.csv`
  - XBRL tables do **not** store `pced_file/pced_row/pced_col`.

### 6. Row Count VerificationAfter each `to_sql()` call (except `stock_info`/`stock_tags` which use `replace` mode), the importer runs `verify_row_count()` to compare the number of rows just imported against `SELECT COUNT(*) FROM table WHERE date = ...`. Mismatches are logged with `❌ Row count mismatch`.

### 7. Fail-Fast Error Handling
Any import error immediately writes the error and traceback to `/app/error_importer.log` and exits with `SystemExit(1)`. The importer does **not** silently skip failed imports.

### 8. Database Wait Logic
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
  START_DATE=$date END_DATE=$date docker compose run --rm importer python import_daily.py
done
```

### Import Monthly Revenue
```bash
# After scraping and processing
docker compose run --rm -e START_DATE=20260101 -e END_DATE=20260101 importer python import_monthly.py
```

### Import Quarterly Reports
```bash
# Use YYYYQX format for quarterly reports
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 importer python import_quarterly.py
```

### Import Quarterly XBRL
```bash
# Use YYYYQX format for quarterly xbrl
docker compose run --rm -e START_DATE=2025Q3 -e END_DATE=2025Q3 importer python import_quarterly_xbrl.py
```

### Force Reimport TDCC Data
```bash
# Delete existing data and reimport
docker compose run --rm -e FORCE_REIMPORT=1 -e START_DATE=20260207 -e END_DATE=20260207 importer python import_weekly.py
```

## Database Schema Notes

### Date Column Types
All `date` columns use **TEXT** type (not DATE), storing values as:
- Daily data: "YYYY-MM-DD" (e.g., "2026-02-01")
- Quarterly data: "YYYYQX" (e.g., "2025Q3")

### Symbol Column Types
**STRICTLY TEXT**: All `symbol` columns in all tables are of type **TEXT** to prevent leading zero loss and ensure JOIN consistency.

### Daily Quotes Table
**No pe_ratio**: The `daily_quotes` table does not contain the `pe_ratio` column. Use the standalone `pe_ratio` table for valuation data.

### Flow Statements (Income/Cash Flow/Reports)
**Dual-Column Schema**: These tables contain both `_q` (single-quarter) and `_acc` (accumulated) versions of each flow-based field (e.g., `eps_q` and `eps_acc`). Data is prepared by the processor via subtractive calculation.

### Bid/Ask in daily_quotes`bid` and `ask` fields are **TEXT** type in the database (preserved from source format).

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

**Output**: Immediate failure on first error with details in `error_importer.log`

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

**Output**: `error_importer.log` (only created if validation fails)

**Time**: 1-2 minutes

**Note**: With lineage-based validation enabled per-date, statistical validation is primarily useful for verifying entire date ranges after bulk imports.

### Usage Examples

```bash
# Normal import with automatic statistical validation
START_DATE=20200210 END_DATE=20200210 docker compose run --rm importer python import_daily.py
```

### Interpreting Validation Reports

#### error_importer.log (Statistical Report)
```
### daily_quotes
- total_rows: CSV=3075602, DB=2666920
- sum_volume: CSV=2009784413610.00, DB=1876122350426.00, 差異=6.6506%
```

**What to check**:
- Row count differences > 10% → investigate
- Numeric differences > 1% → investigate
- Small differences (< 0.1%) → likely rounding/filtering, acceptable

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

### Implementation Details

**Files**:
- `validator.py`: Statistical validation logic
- `import_daily.py`, `import_weekly.py`, `import_monthly.py`, `import_quarterly.py`, `import_quarterly_xbrl.py`: Frequency-based import entry points

**Key Functions**:
```python
# Statistical validation
from validator import validate_all_tables
all_passed, all_errors = validate_all_tables(engine)
```

**Validation runs automatically** - no need to manually invoke unless debugging.

## Next Steps

After importing, data flows to:
- **Calculator** (`calculator/CLAUDE.md`) - Computes technical indicators
- **Backend API** (`backend/CLAUDE.md`) - Serves data to frontend
