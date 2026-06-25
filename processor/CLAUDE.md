# Processor Module Guide

This document describes the actual current architecture and operating rules of `processor` (legacy paths like `data_quality_checker*` and `convert_shareholding_div.py` are removed).

## Overview

`processor` converts data from `data/raw` to `data/processed`, then runs data audits immediately. If an audit fails, the process must stop.

### 🔴 STRICT IMAGE REBUILD RULE (CORE MANDATE)

`processor` does not mount source code into `/app`. After any code change in `processor/`, you **MUST** rebuild before running:

```bash
docker compose build processor
```

If you skip rebuild, container runtime may execute stale code even when host files look updated.

- Input: `data/raw/...`
- Output: `data/processed/...`
- Error log: `/app/error_processor.log`

## Entry Points

Unified entry points:

- `convert_daily.py`
- `convert_weekly.py`
- `convert_monthly.py`
- `convert_quarterly_xbrl.py` — 季報 XBRL（statement-level + `quarterly_reports_xbrl`）
- `audit.py` (standalone audit)

Default Docker `processor` service command:
- `python convert_daily.py`

> 舊的 `convert_quarterly.py`（含 `reports`/`statements`/`detail_xbrl`/`all` 模式，餵舊版 `quarterly_reports`/`income_statement`/`balance_sheet`/`cash_flow`）已 deprecated，移到 `processor/_deprecated/`。對應的 `quarterly/convert_*.py`、`audit_*.py`、`quarterly_statements_converter_common.py` 也搬到 `processor/quarterly/_deprecated/`。

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
  - XBRL converters：
    - `convert_xbrl.py`：產出 statement-level XBRL（`balance_sheet_xbrl` / `income_statement_xbrl` / `cash_flow_xbrl` + `xbrl_codebook`）
    - `convert_quarterly_reports_xbrl.py`：產出 `quarterly_reports_xbrl` 寬表
  - `_deprecated/`：已停用的舊版 converters / audits（`convert_quarterly_reports.py`、`convert_income_statements.py`、`convert_balance_sheet.py`、`convert_cash_flow.py`、`audit_*.py`、`quarterly_statements_converter_common.py`）

## Strict Date Rules (Required)

All converters now follow strict date rules:

- `START_DATE` and `END_DATE` are both required
- Invalid format must `exit(1)`
- `START_DATE > END_DATE` must `exit(1)`
- Missing any required parameter must fail fast with `exit(1)` and write an error to `/app/error_processor.log`; silent fallback/default behavior that continues broad or full processing is strictly forbidden.

Expected format by entry point:

- `convert_daily.py`: `YYYYMMDD`
- `convert_weekly.py`: `YYYYMMDD`
- `convert_monthly.py`: at least `YYYYMM` prefix (can be `YYYYMMDD`)
- `convert_quarterly_xbrl.py`: `YYYYQX`（START_DATE 與 END_DATE 必須相等，單季處理）

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

Quarterly XBRL:

- 透過 `convert_quarterly_xbrl.py` 一鍵處理 statement-level + `quarterly_reports_xbrl`，不再使用 `QUARTERLY_TASK` / `QUARTERLY_STATEMENT_CATEGORIES`。

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

# 4) Quarterly XBRL（statement-level + quarterly_reports_xbrl 一鍵）
START_DATE=2025Q4 END_DATE=2025Q4 docker compose run --rm processor python convert_quarterly_xbrl.py

# 5) Standalone audit (single date only)
START_DATE=20240102 END_DATE=20240102 docker compose run --rm processor python audit.py
```

`convert_quarterly_xbrl.py` 會依序執行：
1. `quarterly/convert_xbrl.py`（statement-level）：
   - `processed/balance_sheet_xbrl/.../all.csv`
   - `processed/cash_flow_xbrl/.../all_accumulated.csv`
   - `processed/income_statement_xbrl/.../all_quarter.csv`（Q4 由 `Q4_acc - Q3_acc` 反推；缺則 fallback `Q4_acc`）
   - `processed/income_statement_xbrl/.../all_accumulated.csv`
   - `processed/xbrl_codebook.csv`
2. `quarterly/convert_quarterly_reports_xbrl.py`：
   - `processed/quarterly_reports_xbrl/.../all_quarter.csv`
   - `processed/quarterly_reports_xbrl/.../all_accumulated.csv`

XBRL raw filename rules (strict, fail-fast):

- Only allow `YYYYQX_symbol_YYYYMMDD.html`.
- Any raw html that does not match this format must stop conversion immediately.
- For the same quarter and symbol, multiple html files are forbidden; detect and stop immediately.
- `publish_time` in detail_xbrl outputs comes from the filename suffix `YYYYMMDD`.

### `quarterly_reports_xbrl` (current experimental status)

- Current builder script: `processor/quarterly/convert_quarterly_reports_xbrl.py`
- Current outputs:
  - `processed/quarterly_reports_xbrl/YYYY/YYYYQX/all_quarter.csv`
  - `processed/quarterly_reports_xbrl/YYYY/YYYYQX/all_accumulated.csv`
- Output columns include `publish_time` and `period`.
- `publish_time` source rule (strict):
  - Do not read publish_time from `income_statement_xbrl` / `balance_sheet_xbrl` / `cash_flow_xbrl`.
  - Resolve from raw html filename only (`YYYYQX_symbol_YYYYMMDD.html`).
  - If only legacy `YYYYQX_symbol.html` exists (missing `_YYYYMMDD`), stop conversion immediately.
- Symbol inclusion rule (important): if a symbol is missing in `income_statement_xbrl/.../all_quarter.csv`, it is skipped.

Known limitations / potentially inaccurate fields:

- `name`:
  - not emitted in `quarterly_reports_xbrl` output (absent from `OUTPUT_COLUMNS`).
- `nav_per_share`:
  - currently approximated by `3XXX / (3110/10)` (rounded to 2 decimals).
  - this is a practical approximation, not guaranteed to exactly match `quarterly_reports` for all symbols.
- `equity_to_assets_ratio`:
  - may differ slightly from `quarterly_reports` due to calculation source/rounding differences.
- `current_ratio`:
  - usually very close to `quarterly_reports`, but may still show tiny floating-point precision differences.
- `quick_ratio`:
  - currently the largest systematic mismatch; formula/available XBRL components do not fully reproduce `quarterly_reports` values.
- `market`:
  - normalized from XBRL market text (`listed* -> sii`, `otc|over-the-counter -> otc`), but rare mismatches can still occur.
- `period`:
  - intentionally exists in `quarterly_reports_xbrl` (`all_quarter.csv` / `all_accumulated.csv`) but not in legacy `quarterly_reports`.
- lineage columns:
  - `src_file`, `src_row`, `src_col` are not emitted in `quarterly_reports_xbrl` (absent from `OUTPUT_COLUMNS`).

`*_acc_ly` and `*_acc_yoy` notes:

- For normal years, values are derived from prior-year same-quarter XBRL accumulated data.
- For early-history quarters with no prior-year XBRL baseline (for example 2020Q1), these fields can be empty.
- In current batch workflow, empty `*_acc_ly` / `*_acc_yoy` may be backfilled from `processed/quarterly_reports/.../all.csv` after generation.

## Data Lineage & Schema Enforcement

All processed CSVs must include lineage columns:

- `pced_file`: raw file path
- `pced_row`: raw file row number (1-based)
- `pced_col`: source-column mapping (for example `x#x#1#2#...`)

**Schema enforcement (single source of truth):**
Before writing CSV, the generic daily/weekly/monthly path enforces schema from `common/schemas.py`. This guarantees stable types before DB import (for example, `symbol` must be string, numeric fields must be `Float64`).

> Exception — quarterly XBRL converters bypass `SCHEMA_COLS`: `convert_quarterly_reports_xbrl.py` writes via `csv.DictWriter(fieldnames=OUTPUT_COLUMNS)` directly (its own `OUTPUT_COLUMNS` list), with no `common/schemas.py` enforcement. Only the daily/weekly/monthly generic path applies `schemas.py`.

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
  - 註：以上是 raw-header 的 COL_MAP 對應；這些 `last_*` 欄位會被 `SCHEMA_COLS["daily_quotes"]`（只保留 `bid`/`ask`）丟棄，不會進入最終 processed `daily_quotes` CSV。
- **Financial statements dual-track (XBRL)**：`quarterly_reports_xbrl` 與 `income_statement_xbrl` 同時存在 `quarter` 與 `accumulated` 兩種 `period_type`。Q4 single-quarter 是 `Q4_acc - Q3_acc` 反推（缺前期則 fallback `Q4_acc`），歷史 backfill 仍須依季別順序跑。
  - 注：legacy 的 `quarterly_reports` / `income_statement` / `balance_sheet` / `cash_flow` 表已停止寫入，相關處理流程在 `_deprecated/`。
- **Important change**: `daily_quotes` no longer includes `pe_ratio` (to keep SII/OTC consistent). PE data is handled by standalone `pe_ratio` category.
- `margin_summary` is a derived category: it is generated from `raw/margin_trading/*` and written to `processed/margin_summary/.../all.csv` (there is no `raw/margin_summary` input folder).
- Some sources include trailing unnamed columns; mapping already handles these to avoid parse failures.
- Shell scripts aligned to new entry points:
  - `schedules/daily_update.sh`
  - `schedules/weekly_update.sh`
  - `schedules/monthly_update.sh`
  - `schedules/xbrl_scrape_daily.sh`（每日 scrape，systemd 排程）
  - `schedules/xbrl_process_import.sh`（公告期末/補資料用，process+import）
