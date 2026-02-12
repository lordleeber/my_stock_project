# Processor Module Guide (for AI Assistants)

This guide covers the data processing component of the Taiwan stock market analysis pipeline.

## Overview

The processor cleans and standardizes raw CSV data from the scraper:
- Converts Chinese column names to English
- Handles multi-line headers
- Normalizes numeric formats (removes commas, handles missing values)
- Validates data integrity
- Performs integrated quality checking

**Input**: `data/raw/` (from scraper)
**Output**: `data/processed/` (standardized CSVs ready for database import)

## Architecture (v3.2)

**Date-First Processing Loop**: Changed from category-first to date-first architecture. The processor now:
1. Scans all category directories to collect unique dates
2. Validates date format (YYYYMMDD) to prevent path traversal
3. Sorts dates chronologically
4. For each date:
   - Processes all categories (daily_quotes, institutional_investors, etc.)
   - **Injects Data Lineage**: Adds `src_file`, `src_row`, `src_col` to every row.
   - Runs integrated quality check (data_quality_checker.main())
   - **Full Column-Level Verification**: QC verifies ALL columns (not just identity columns) by cross-referencing processed data with raw source files.
   - **Immediate Stop on Error**: If any verification fails, processing stops immediately. Subsequent dates are NOT processed.
   - Restores environment variables after QC

**Data Lineage & Traceability (Column-level)**: Every processed row contains audit columns for full traceability:
- `src_file`: Relative path to the raw source file (e.g., `data/raw/daily_quotes/2020/20200102/sii.csv`)
- `src_row`: 1-based line number in the original raw file (e.g., `186`)
- `src_col`: **Column-level lineage mapping** in format `x#x#1#2#3#4#...` where:
  - `x` = Column added during processing (e.g., `date`, `market`)
  - Numbers = 1-based column indices from raw CSV (e.g., `1` = first column, `2` = second column)
  - `#` = Delimiter separating each field's source column
  - Example: `x#x#1#2#3#4#5` means: date(x), market(x), symbol(col 1), name(col 2), open(col 3), high(col 4), low(col 5)

## Modules

| Module | Purpose |
|--------|---------|
| `convert.py` | **Unified ETL entry point with integrated QC**: Date-first processing loop that runs quality checks after each date. Auto-dispatches to correct handler based on category. Handles stocks, summaries, and indices. **Now injects lineage metadata.** |
| `convert_quarterly_reports.py` | Handles SII/OTC quarterly reports from CSV files (switched from XLS). **Now injects lineage metadata** with index-based column mapping. SII has pretax columns (19-21), OTC calculates pretax from op_income + non_op_income. **Outputs to YYYY/YYYYQX/all.csv**. |
| `convert_monthly_revenue.py` | Handles monthly revenue data processing. **Now injects lineage metadata** with strict column mapping validation. **Outputs to YYYY/YYYYMXX/all.csv**. |
| `convert_quarterly_statements.py` | Handles MOPS quarterly statements (income_statement, balance_sheet, cash_flow). **Now injects lineage metadata**. Supports multiple statement types (general, bank, table, insurance) with flexible column mapping. **Outputs to YYYY/YYYYQX/all.csv**. |
| `convert_shareholding.py` | **Current**: Handles all-in-one TDCC shareholding format from `shareholding/YYYY/` (OpenData API). **Outputs to YYYY/YYYYMMDD.csv**. |
| `convert_shareholding_div.py` | **Legacy**: Handles per-stock TDCC shareholding format from `shareholding_div/` (2023/09~2026/02). |
| `validator.py` | Validates row counts and numeric accuracy (Raw vs Processed) |
| `data_quality_checker.py` | **Main QC orchestrator** that runs category-specific checkers. Stops immediately on first error. |
| `data_quality_checker_base.py` | **Base class** for all category checkers. Provides shared lineage verification, value comparison, and error handling. |
| `data_quality_checker_*.py` | **Category-specific checkers** (10 files): `daily_quotes`, `institutional_investors`, `margin_trading`, `margin_sbl`, `pe_ratio`, `foreign_holding`, `market_indices`, `institutional_summary`, `margin_summary`, `monthly_revenue`. Each handles type-specific comparison (int/float conversion, string matching, transformation mapping). |
| `schemas.py` | Column mappings, numeric types, standard schema definitions. **All columns must have mappings** (unknown columns cause errors). **Includes index-specific fields** (index_name, index_close, index_change_points) separate from stock fields. All schemas include src_file, src_row, src_col. |
| `utils.py` | Shared helpers: **Header merging for multi-line CSVs**, index extraction, CSV parsing with encoding fallback. **`read_raw_csv` returns column mapping** for accurate src_col generation after schema enforcement. **`clean_dataframe` enforces strict column mapping** (raises error on unknown columns). |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `START_DATE` | today | YYYYMMDD format |
| `END_DATE` | today | YYYYMMDD format |
| `FORCE_REPROCESS` | 0 | Set to 1 to reprocess already-processed files |
| `DEBUG` | 0 | Set to 1 to enable verbose logging (success messages, row mismatch warnings, skip notifications) |
| `RAW_DIR` | /app/data/raw | Input directory path |
| `PROCESSED_DIR` | /app/data/processed | Output directory path |

## Docker Service

```bash
# Process daily data for a specific date
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor

# Enable debug mode for detailed output (useful for troubleshooting)
DEBUG=1 START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor

# Force reprocess existing files
FORCE_REPROCESS=1 START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
```

**Important**: Always rebuild after code changes:
```bash
docker compose build processor
```

## Advanced Processing Features

### 1. Date-First Processing Loop (v3.0)
Changed from category-first to date-first architecture. Processes all categories for each date, then immediately runs quality checks before moving to the next date. This ensures data integrity per-date rather than per-category.

### 2. Integrated Quality Checking
`data_quality_checker.main()` is now called automatically after processing each date. The environment variables `START_DATE` and `END_DATE` are temporarily set to the current date during QC execution, then restored to prevent side effects.

### 3. Path Traversal Protection
Date strings are validated with regex pattern `^\d{8}$` before being used in file paths, preventing malicious directory names like `date=../../etc/passwd`.

### 4. Dual Error Logging System
- `log_processing_error()`: Records ETL runtime errors (convert.py)
- `log_parsing_error()`: Records CSV parsing errors (utils.py)
- Both write to `/app/error_processor.md` with timestamps and context

### 5. Debug Mode
Set `DEBUG=1` to enable verbose output:
- ✓ CSV parsing success messages with row counts
- ⚠️ Row length mismatch statistics
- ⚠️ Invalid date format warnings
- Skip notifications for already-processed files

### 6. Incremental Processing
By default, skips files that already exist in the processed directory. Set `FORCE_REPROCESS=1` to force reprocessing.

### 7. Multi-line Header Merging
`utils.read_raw_csv` automatically detects and merges category-subheader rows (common in TWSE/TPEx CSVs).

Example:
```
Row 1: 融資,融資,融券,融券
Row 2: 買進,賣出,買進,賣出
```
Merged to: `融資-買進`, `融資-賣出`, `融券-買進`, `融券-賣出`

### 8. Encoding Fallback with Replace
Attempts UTF-8-sig first, falls back to CP950 with `errors='replace'` (preserves decode failure markers `` instead of silently discarding).

### 9. Row Length Validation
Tracks and reports mismatched row lengths during CSV parsing. In DEBUG mode, displays count of adjusted rows per file.

### 10. Quarterly Report Parsing (SII)
Handles complex multi-row headers (Rows 2-5) in 2025+ SII Excel files by locating the first row with a 4-digit numeric symbol and using fixed index-based mapping (Col 13: EPS, Col 20: Op Cash Flow).

### 11. Market Index Extraction
- **SII**: Extracted from `daily_quotes/sii.csv` via `utils.read_sii_indices`.
- **OTC**: Fetched as a dedicated category using modernized TPEx JSON-to-CSV APIs.

## Column Mapping

The processor converts Chinese column names to English using `processor/schemas.py`:

**Mapping Policy (v3.1):**
- ✅ **Strict Mapping Required**: All columns must have a mapping in COLUMN_MAP. Unknown columns will cause processing to fail with an error message asking you to add the mapping.
- ✅ **Index-Specific Fields**: Market indices use separate field names to avoid conflicts with stock data:
  - `index_name`, `index_close`, `index_change_points` (for indices)
  - `symbol`, `name`, `close`, `change` (for stocks)
- ✅ **SII/OTC Variants**: Different column names from SII and OTC markets can map to the same standard field (e.g., "證券代號" and "代號" both map to "symbol")

**Key mappings:**

**Basic Fields:**
- 證券代號 → symbol
- 證券名稱 → name
- 成交股數 → volume
- 成交金額 → value
- 成交筆數 → transactions

**OHLC:**
- 開盤價 → open
- 收盤價 → close
- 最高價 → high
- 最低價 → low
- 漲跌(+/-) → change
- 漲跌價差 → change

**Institutional:**
- 外陸資買賣超股數 → foreign_net
- 投信買賣超股數 → trust_net
- 自營商買賣超股數(自行買賣) → dealer_net

**Margin:**
- 融資 → margin_long
- 融券 → margin_short
- 買進 → buy
- 賣出 → sell

## Validation & Quality Checking

### Standalone Validator (Row Count Verification)
```bash
docker compose run --rm processor python validator.py
```

Compares row counts between raw and processed files to ensure no data loss.

### Quality Checker (Full Column-Level Verification)
```bash
# Now runs automatically in convert.py, but can be run standalone
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor python data_quality_checker.py
```

**Architecture (v3.2)**: Refactored into category-specific checker classes:

| Checker | Category | Special Handling |
|---------|----------|------------------|
| `DailyQuotesChecker` | daily_quotes | OHLCV int→float conversion, OHLC logic validation |
| `InstitutionalInvestorsChecker` | institutional_investors | Buy/sell/net integer columns |
| `MarginTradingChecker` | margin_trading | Margin long/short integers |
| `MarginSblChecker` | margin_sbl | Securities borrowing/lending |
| `PeRatioChecker` | pe_ratio | Float PE values, negative check |
| `ForeignHoldingChecker` | foreign_holding | Shares (int), ratios (float) |
| `MarketIndicesChecker` | market_indices | Index values (float), optional SII |
| `InstitutionalSummaryChecker` | institutional_summary | Chinese→English institution mapping |
| `MarginSummaryChecker` | margin_summary | Derived item names |
| `MonthlyRevenueChecker` | monthly_revenue | YYYYMXX date format, parentheses for negatives |

**Verification Features:**
- ✅ **Full column-level verification**: ALL columns verified, not just identity columns
- ✅ **Type-aware comparison**: Integer columns (volume, transactions) convert float→int; Float columns use tolerance
- ✅ **Transformation handling**: Institution names (Chinese→English), derived columns marked appropriately
- ✅ **Immediate stop on error**: First error stops processing, no subsequent dates processed
- ✅ **Empty marker handling**: Supports `--`, `----`, `除權`, `除息`, `N/A`, etc.
- Writes findings to root `/app/error_processor.md`

## Error Handling & Debugging

### Error Logs

The processor writes detailed error logs to `/app/error_processor.md`:

- **Processing Errors** (`log_processing_error`): ETL runtime errors, missing columns, invalid data
- **Parsing Errors** (`log_parsing_error`): CSV format issues, encoding problems, header detection failures

Each error entry includes:
- Timestamp
- Date being processed (YYYYMMDD)
- Category (if applicable)
- Error message and Python traceback

### Debug Mode Usage

Enable debug mode to see detailed processing information:

```bash
# Local debugging with verbose output
DEBUG=1 START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor

# Production mode (default) - minimal output
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
```

**Debug mode shows**:
- ✓ Successful CSV parsing with row counts
- ⚠️ Row length mismatches (e.g., "42 rows adjusted for length mismatch")
- ⚠️ Invalid date format warnings (path traversal prevention)
- ℹ️ Skip notifications for already-processed files

### Troubleshooting Common Issues

**Issue**: No data processed even though raw files exist
- **Solution**: Check if processed files already exist. Set `FORCE_REPROCESS=1` to override.

**Issue**: Quality check fails with exit code 1
- **Solution**: Check `/app/error.md` (written by data_quality_checker). Common causes: NULL values in critical columns, missing output files.

**Issue**: "Invalid date format ignored" warnings
- **Solution**: Check raw data directories for malformed `date=` folders. Manually remove or rename invalid directories.

**Issue**: Encoding errors or garbled Chinese characters
- **Solution**: Verify scraper output is UTF-8-sig. Processor automatically falls back to CP950 with replacement markers.

**Issue**: Row length mismatch warnings
- **Solution**: Enable DEBUG mode to see which files have issues. Usually caused by inconsistent column counts in TWSE/TPEx CSVs. Processor auto-adjusts but may indicate upstream data quality issues.

## Special Data Processing

### Shareholding Data (TDCC)

#### Current: All-in-One Format (from OpenData API)
```bash
# Process data from shareholding/ directory (default, supports year subfolders)
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor python convert_shareholding.py
```

#### Legacy: Per-Stock Format (2023/09~2026/02)
```bash
START_DATE=20230915 END_DATE=20260206 docker compose run --rm processor python convert_shareholding_div.py
```

All scripts output to the same `data/processed/shareholding_div/` directory.

### Monthly Revenue
```bash
START_DATE=20260101 END_DATE=20260101 docker compose run --rm processor python convert_monthly_revenue.py
```

### Quarterly Reports
```bash
# Processes SII/OTC reports and MOPS statements
START_DATE=2025Q3 END_DATE=2025Q3 docker compose run --rm processor python convert_quarterly_reports.py
START_DATE=2025Q3 END_DATE=2025Q3 docker compose run --rm processor python convert_quarterly_statements.py --category income_statement
```

## Column-Level Lineage Tracking (v3.1)

### Overview
Every processed row includes precise traceability to the raw source file, allowing you to trace each field back to its original location.

### How It Works

**1. During CSV Reading (`utils.read_raw_csv`):**
```python
# For each data row, record its source columns (1-based)
# Example raw CSV: 證券代號,證券名稱,成交股數,成交金額,開盤價
# Generated src_col: "1#2#3#4#5"
```

**2. During Processing (`convert.py`):**
```python
# Add processing-time columns (date, market)
# Update src_col to reflect these additions
# Final src_col: "x#x#1#2#3#4#5"
#                ^^^  Added columns
#                    ^^^^^^^^^ Original columns
```

**3. Example Lineage Record:**
```csv
date,market,symbol,name,volume,value,open,src_file,src_row,src_col
2020-01-02,sii,0050,元大台灣50,1000000,100000000,97.05,data/raw/daily_quotes/2020/20200102/sii.csv,186,x#x#1#2#3#4#5
```

**Decoding src_col `x#x#1#2#3#4#5`:**
- Position 1 (`date`): `x` → Added during processing
- Position 2 (`market`): `x` → Added during processing
- Position 3 (`symbol`): `1` → Column 1 in raw CSV (證券代號)
- Position 4 (`name`): `2` → Column 2 in raw CSV (證券名稱)
- Position 5 (`volume`): `3` → Column 3 in raw CSV (成交股數)
- Position 6 (`value`): `4` → Column 4 in raw CSV (成交金額)
- Position 7 (`open`): `5` → Column 5 in raw CSV (開盤價)

### Quality Verification

**Lineage Verification (data_quality_checker_*.py):**
- Verifies **all rows** and **all columns** (not just identity columns)
- Cross-references processed data with raw files using src_file, src_row, src_col
- **Type-aware comparison**:
  - Integer columns (volume, transactions, shares): float→int conversion before comparison
  - Float columns (prices, ratios): tolerance-based comparison (0.0001 for prices, 0.01% for percentages)
  - String columns: direct comparison with quote/whitespace normalization
- **Transformation tracking**: Columns that undergo mapping (institution names) or derivation (item names) are handled specially
- **Immediate termination**: Any mismatch stops processing immediately
- Reports any mismatches in `error_processor.md`

### Benefits

✅ **Complete Audit Trail**: Know exactly where each data point came from
✅ **Data Quality**: Verify processing accuracy by tracing back to source
✅ **Debugging**: Quickly identify which raw file/column caused issues
✅ **Compliance**: Full lineage for regulatory requirements

## Known Data Gaps & Market Rules

### OTC Index Holidays (Trading Closed)
The following dates correctly return no data for OTC indices due to market closures:
- **2022-02-04**: Lunar New Year Holiday
- **2023-01-18**: Market Closing Day (Last trading day before Lunar New Year)
- **2024-10-31**: Typhoon Kong-rey
- **Weekends/National Holidays**: No data for any market category.

### Important Pipeline Behaviors

1. **Fail-fast on QC errors**: If any data quality check fails, processing stops immediately. Subsequent dates are NOT processed. This ensures data integrity issues are caught and fixed before continuing.
2. **Environment variable isolation**: QC runs use temporary environment variable overrides that are automatically restored via finally blocks, preventing interference with the main processing loop.
3. **market_indices extraction**: Processor auto-extracts market indices from daily_quotes during conversion.
4. **src_col generation**: The `src_col` is generated AFTER `enforce_schema()` reorders columns, ensuring indices match the final SCHEMA_COLS order (not the raw CSV order).

## Next Steps

After processing, data flows to:
- **Importer** (`importer/CLAUDE.md`) - Loads processed CSVs into PostgreSQL
