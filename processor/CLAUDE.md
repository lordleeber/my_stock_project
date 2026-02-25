# Processor Module Guide

This document describes the actual current architecture and operating rules of `processor` (legacy paths like `data_quality_checker*` and `convert_shareholding_div.py` are removed).

## Overview

`processor` converts data from `data/raw` to `data/processed`, then runs data audits immediately. If an audit fails, the process must stop.

- Input: `data/raw/...`
- Output: `data/processed/...`
- Error log: `/app/error_processor.log`

## Entry Points

Unified entry points:

- `convert_daily.py`
- `convert_weekly.py`
- `convert_monthly.py`
- `convert_quarterly.py`
- `audit.py` (standalone audit)

Default Docker `processor` service command:
- `python convert_daily.py`

## Folder Structure

- `daily/`
  - converters: `convert_daily_quotes.py`, `convert_institutional_investors.py`, `convert_foreign_holding.py`, `convert_margin_trading.py`, `convert_margin_sbl.py`, `convert_pe_ratio.py`, `convert_market_indices.py`, `convert_institutional_summary.py`, `convert_margin_summary.py`
  - audits: `audit_daily_quotes.py`, `audit_institutional_investors.py`, `audit_foreign_holding.py`, `audit_margin_trading.py`, `audit_margin_sbl.py`, `audit_pe_ratio.py`, `audit_market_indices.py`, `audit_institutional_summary.py`, `audit_margin_summary.py`

- `weekly/`
  - converter: `convert_shareholding.py`
  - audit: `audit_shareholding.py`

- `monthly/`
  - converter: `convert_monthly_revenue.py`
  - audit: `audit_monthly_revenue.py`

- `quarterly/`
  - reports: `convert_quarterly_reports.py` + `audit_quarterly_reports.py`
  - statements:
    - `convert_income_statements.py` + `audit_income_statements.py`
    - `convert_balance_sheet.py` + `audit_balance_sheet.py`
    - `convert_cash_flow.py` + `audit_cash_flow.py`
  - shared common:
    - `quarterly_statements_converter_common.py`
    - `audit_quarterly_common.py`

## Strict Date Rules (Required)

All converters now follow strict date rules:

- `START_DATE` and `END_DATE` are both required
- Invalid format must `exit(1)`
- `START_DATE > END_DATE` must `exit(1)`

Expected format by entry point:

- `convert_daily.py`: `YYYYMMDD`
- `convert_weekly.py`: `YYYYMMDD`
- `convert_monthly.py`: at least `YYYYMM` prefix (can be `YYYYMMDD`)
- `convert_quarterly.py`: `YYYYQX`

`audit.py` rules:

- `START_DATE` and `END_DATE` are required (`YYYYMMDD`)
- Currently supports single-day audit only: `START_DATE == END_DATE`

## Environment Variables

Common:

- `START_DATE` (required)
- `END_DATE` (required)
- `FORCE_REPROCESS` (optional, `1` means reprocess)
- `DEBUG` (optional)
- `RAW_DIR` (default `/app/data/raw`)
- `PROCESSED_DIR` (default `/app/data/processed`)

Quarterly-specific:

- `QUARTERLY_TASK`: `reports` | `detail_xbrl` | `statements` | `all` (default `all`)
- `QUARTERLY_STATEMENT_CATEGORIES`: `income_statement,balance_sheet,cash_flow` (optional subset)

Audit output controls:

- `AUDIT_PRINT_COLUMNS` (default `0`, disables per-column verbose output)
- `AUDIT_SYMBOL` (default `2330`, used when per-column output is enabled)

## Common Commands

```bash
# 1) Daily convert + integrated audits
START_DATE=20240102 END_DATE=20240102 docker compose run --rm processor python convert_daily.py

# 2) Weekly shareholding
START_DATE=20240105 END_DATE=20240105 docker compose run --rm processor python convert_weekly.py

# 3) Monthly revenue
START_DATE=20240101 END_DATE=20240131 docker compose run --rm processor python convert_monthly.py

# 4) Quarterly: reports + 3 statements
START_DATE=2024Q1 END_DATE=2024Q1 docker compose run --rm processor python convert_quarterly.py

# 5) Quarterly: only statements, only income_statement
QUARTERLY_TASK=statements QUARTERLY_STATEMENT_CATEGORIES=income_statement \
START_DATE=2024Q1 END_DATE=2024Q1 docker compose run --rm processor python convert_quarterly.py

# 6) Quarterly: detail XBRL facts (raw html -> processed csv)
QUARTERLY_TASK=detail_xbrl START_DATE=2025Q3 END_DATE=2025Q3 \
docker compose run --rm processor python convert_quarterly.py

# 7) Standalone audit (single date only)
START_DATE=20240102 END_DATE=20240102 docker compose run --rm processor python audit.py
```

## Data Lineage & Schema Enforcement

All processed CSVs must include lineage columns:

- `pced_file`: raw file path
- `pced_row`: raw file row number (1-based)
- `pced_col`: source-column mapping (for example `x#x#1#2#...`)

**Schema enforcement (single source of truth):**
Before writing CSV, processor must enforce schema from `common/schemas.py`. This guarantees stable types before DB import (for example, `symbol` must be string, numeric fields must be `Float64`).

**Strict symbol filtering:**
For categories with `symbol`, keep only 4-digit numeric symbols. This excludes ETFs, warrants, preferred shares, and REITs.

`audit_*` modules validate values using `pced_file/pced_row/pced_col`. Any mismatch must stop the pipeline and write to `/app/error_processor.log`.

## Runtime Behavior

- Convert success is followed by immediate audit (not delayed to end of full batch)
- Any audit failure must stop the remaining dates/categories
- After any code change, the official workflow is to rebuild the image:

```bash
docker compose build processor
```

- Do not manually `cp` code into containers/images to bypass rebuild. That creates mismatch between runtime code and repository state, making results non-reproducible and debugging unreliable.

## Notes

- Legacy files (for example `data_quality_checker*.py`, `convert_shareholding_div.py`, `convert_quarterly_statements.py`) are no longer used.
- Daily quotes mapping uses `last_*` naming:
  - `最後買價 -> last_bid`
  - `最後賣價 -> last_ask`
  - `最後買量(千股)/(張數) -> last_bid_volume`
  - `最後賣量(千股)/(張數) -> last_ask_volume`
- **Financial statements dual-track**: `quarterly_reports`, `income_statement`, `cash_flow` include both `_q` (single quarter) and `_acc` (accumulated) fields.
  - **Single-quarter logic**: For Q2~Q4, processor reads previous quarter processed CSV and calculates `q = current_acc - prev_acc`. If historical data is missing, fallback is `q = acc`.
  - **Run order**: Because of temporal dependency, historical backfills must run in chronological order (for example `2024Q1 -> Q2 -> Q3 ...`).
- **Important change**: `daily_quotes` no longer includes `pe_ratio` (to keep SII/OTC consistent). PE data is handled by standalone `pe_ratio` category.
- `margin_summary` is a derived category: it is generated from `raw/margin_trading/*` and written to `processed/margin_summary/.../all.csv` (there is no `raw/margin_summary` input folder).
- Some sources include trailing unnamed columns; mapping already handles these to avoid parse failures.
- Shell scripts aligned to new entry points:
  - `schedules/daily_update.sh`
  - `schedules/weekly_update.sh`
  - `schedules/monthly_update.sh`
  - `schedules/quarterly_update.sh`
