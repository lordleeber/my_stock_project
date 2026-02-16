# Processor Module Guide

這份文件描述目前 `processor` 的實際架構與操作方式（已移除舊制 `data_quality_checker*` / `convert_shareholding_div.py` 等路徑）。

## Overview

Processor 會把 `data/raw` 轉成 `data/processed`，並在轉換後立即進行資料稽核（audit），有錯誤就立刻停止。

- Input: `data/raw/...`
- Output: `data/processed/...`
- Error log: `/app/error_processor.log`

## Entry Points

目前統一入口如下：

- `convert_daily.py`
- `convert_weekly.py`
- `convert_monthly.py`
- `convert_quarterly.py`
- `audit.py`（可獨立執行稽核）

Docker `processor` service 預設 command 為：
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

現在所有 converter 都是「完全新制」：

- `START_DATE`、`END_DATE` **必填且缺一不可**
- 格式錯誤會直接 `exit(1)`
- `START_DATE > END_DATE` 會直接 `exit(1)`

各入口格式：

- `convert_daily.py`: `YYYYMMDD`
- `convert_weekly.py`: `YYYYMMDD`
- `convert_monthly.py`: 至少需有 `YYYYMM` 前綴（可給 `YYYYMMDD`）
- `convert_quarterly.py`: `YYYYQX`

`audit.py` 規則：

- `START_DATE`、`END_DATE` 必填（`YYYYMMDD`）
- 目前只支援單日稽核：`START_DATE == END_DATE`

## Environment Variables

共用：

- `START_DATE`（必填）
- `END_DATE`（必填）
- `FORCE_REPROCESS`（可選，`1` 表示重跑）
- `DEBUG`（可選）
- `RAW_DIR`（預設 `/app/data/raw`）
- `PROCESSED_DIR`（預設 `/app/data/processed`）

Quarterly 專用：

- `QUARTERLY_TASK`: `reports` | `statements` | `all`（預設 `all`）
- `QUARTERLY_STATEMENT_CATEGORIES`: `income_statement,balance_sheet,cash_flow`（可選子集合）

Audit 詳細列印控制：

- `AUDIT_PRINT_COLUMNS`（預設 `0`，關閉逐欄列印）
- `AUDIT_SYMBOL`（預設 `2330`，當開啟逐欄列印時生效）

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

# 6) Standalone audit (single date only)
START_DATE=20240102 END_DATE=20240102 docker compose run --rm processor python audit.py
```

## Data Lineage & Schema Enforcement

所有 processed CSV 都包含 lineage 欄位：

- `pced_file`: raw 檔案路徑
- `pced_row`: raw 檔案行號（1-based）
- `pced_col`: 欄位來源映射（例如 `x#x#1#2#...`）

**Schema 強制執行 (Single Source of Truth):**
Processor 在存入 CSV 之前，會引用 `common/schemas.py` 定義的 Schema 進行強制型別轉換。這確保了產出的 CSV 檔案在匯入資料庫前就已經具備正確的資料型別（例如 `symbol` 必為字串，數值欄位必為 `Float64`）。

**嚴格股票過濾:**
所有包含 `symbol` 欄位的類別都會執行嚴格過濾：**僅保留 4 碼純數字代號**。這會自動排除 ETF (如 0050)、權證、特別股及 REITs。

`audit_*` 會依 `pced_file/pced_row/pced_col` 做欄位級比對，發現 mismatch 即停止流程並寫入 `/app/error_processor.log`。

## Runtime Behavior

- Convert 成功後會立即執行對應 audit（不是全部存完才檢查）
- 任一類別 audit 失敗：立刻停止，不繼續後續日期/類別
- 建議任何程式碼變更後先重建：

```bash
docker compose build processor
```

## Notes

- 舊制檔名（如 `data_quality_checker*.py`, `convert_shareholding_div.py`, `convert_quarterly_statements.py`）不再使用。
- Daily quotes 欄位映射採用 `last_*` 命名：
  - `最後買價 -> last_bid`
  - `最後賣價 -> last_ask`
  - `最後買量(千股)/(張數) -> last_bid_volume`
  - `最後賣量(千股)/(張數) -> last_ask_volume`
- **財務報表雙軌制**: `quarterly_reports`, `income_statement`, `cash_flow` 現在具備 `_q` (單季) 與 `_acc` (累計) 雙軌欄位。
  - **單季計算邏輯**: Processor 在處理 Q2~Q4 時，會自動讀取前一季的 `processed` CSV 檔案，將當前累計值減去前一季累計值以算出單季值。若無歷史資料則預設 `q = acc`。
  - **計算順序**: 由於具備時序依賴性，重跑歷史資料時**必須按照時間順序**（如 2024Q1 -> Q2 -> Q3...）執行。
- **重要變更**: `daily_quotes` 不再包含 `pe_ratio` 欄位（以確保 SII/OTC 一致性）。本益比資料現在統一由獨立的 `pe_ratio` 類別處理。
- 部分來源會有未命名尾端空欄，目前已納入映射避免 parse 失敗。
- Shell 腳本目前已對齊新入口：
  - `schedules/daily_update.sh`
  - `schedules/weekly_update.sh`
  - `schedules/monthly_update.sh`
  - `schedules/quarterly_update.sh`
