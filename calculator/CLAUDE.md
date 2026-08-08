# Calculator Module Guide (for AI Assistants)

This guide covers the technical indicator calculation component of the Taiwan stock market analysis pipeline.

## Overview

The calculator component refines raw market and financial data into actionable investment insights. It consists of two main pillars:

1.  **Technical Indicators (`calculate_daily.py`)**: Computes MA, RSI, MACD, etc., for price trend analysis.
2.  **Institutional Holding Derivatives (`calculate_trust_holding.py`, `calculate_dealer_holding.py`)**: Computes cumulative trust/dealer held shares and held ratio.
3.  **Shareholding Concentration (`calculate_shareholding_concentration.py`)**: Derives large/small holder concentration metrics from TDCC shareholding buckets.
4.  **Valuation (`calculate_valuation.py`)**: Computes PIT-accurate TTM EPS, PE, PE percentile, and ROE (backward / published-quarter only).

Error handling is fail-fast:
- Any runtime error writes to `/error_calculator.log` or `/error_valuation_calculator.log`
- Exits immediately with non-zero status.
- `abort_with_error` 由 `calculator/_error_report.py::make_abort(ERROR_LOG)` 產生（7 支
  原本各抄一份，其中 6 份還漏了「執行時間」——報告是 `"w"` 覆寫的，沒時間戳就看不出
  是哪次跑留下的）。寫入走 `common/error_log.py`（**fail-soft**）：log 被 docker 建成
  目錄時仍印得出真正的錯誤訊息再 exit 1（見 `RESTORE.md` §落差4）。

### 🔴 STRICT IMAGE REBUILD RULE (CORE MANDATE)

`calculator` does not mount source code into `/app`. After any code change in `calculator/`, you **MUST** rebuild before running:

```bash
docker compose build calculator
```

If you skip rebuild, container runtime may execute stale code even when host files look updated.

---

## Technical Indicators (`calculate_daily.py`)

Computes technical signals from `daily_quotes` and stores results in `technical_indicators`.

### Indicators
- **Moving Averages (MA/VMA)**: 5, 10, 20, 60, 120, 240 days.
- **KD Stochastic**: 9-day alpha=1/3.
- **RSI**: 6 and 12-day.
- **MACD**: DIF (EMA12-26), DEA (EMA9 of DIF), Histogram.
- **Bollinger Bands**: 20-day, 2σ.

---

## Valuation (`calculate_valuation.py`)

Integrates Price, Financial Reports, and historical EPS into a daily snapshot under **Point-in-Time (PIT)** logic.

### Core Logic: Point-in-Time (PIT) Alignment
To avoid look-ahead bias, the calculator anchors financial data to their **official publication deadlines**:
- Q1: May 15 | Q2: Aug 14 | Q3: Nov 14 | Q4: Mar 31.
Every daily valuation record uses the latest report *available at that specific date*.

### TTM EPS
- **`ttm_eps_official`**: Sum of the 4 most recently published single-quarter EPS
  (`eps_q`). Written for **every** row that has a full trailing-4-quarter window —
  **including loss-making stocks where the sum is ≤ 0**. Only rows with fewer than
  4 published quarters (NaN TTM) are dropped.

  > **⚠️ Do NOT re-add a `ttm_eps_official > 0` row filter.** Dropping ≤0 rows was
  > the root cause of issue #2: it left holes that downstream `latest <= date`
  > joins silently forward-filled with a **stale positive** TTM (type A, e.g. 8089
  > stuck at 0.16 across a loss stretch), and **froze persistently loss-making
  > symbols at a one-off spike** (type B, e.g. 6499 frozen at 33.82 from a 2021Q2
  > gain while the true TTM was −8.81). ~18–22% of the tradable universe is
  > loss-making at any cutoff, so this is a large silent contract violation.

### Output Metrics
- **`pe_calculated`**: `close / ttm_eps_official` (computed internally; not persisted
  to DB). **NULL when `ttm_eps_official` ≤ 0** — a negative PE is meaningless and
  would pollute the expanding-rank percentile.
- **`pe_official`**: 官方 PE（從 `pe_ratio` 直接合併；**不依賴** `ttm_eps_official`）。
- **`pe_percentile_official`**: **PIT expanding rank** — for each `(symbol, date)` row,
  rank `pe_calculated` against `{same symbol's PE values with date <= row's date}`. Once
  written, a row's percentile is **frozen** (PIT-safe). Implemented via
  `pandas.expanding().rank(pct=True)` over the historical DB tail concatenated with the
  new batch. **NULL for ≤0-TTM rows** (their `pe_calculated` is NaN and is excluded
  from the ranking, so positive-TTM percentiles are unchanged vs the pre-fix behaviour).
- **`roe_official`**: `ttm_eps_official / nav_per_share * 100`. **Keeps its sign** —
  a negative ROE is a valid feature for loss-making stocks. NULL only when
  `nav_per_share` drives a div-by-zero / ±inf (negative-equity blowups).

### Self-Reconciliation Check (`reconcile_ttm`)
After each insert, the calculator verifies that **every symbol's latest stored
`ttm_eps_official` equals the trailing-4Q `eps_q` sum** published as of that row's
date (tolerance 0.10). Mismatches are logged to stdout + `/error_valuation_calculator.log`
with the worst offenders, but **never abort the run**. A non-empty report flags either a
regression here or a `quarterly_reports_xbrl` restatement the frozen history hasn't
absorbed yet (→ rebuild with `--force-full`).

> **Migration**: `calculator/backfill_pit_percentile.py` is the one-time migration that
> rewrites all historical `pe_percentile_official` rows under the expanding-rank
> semantics. Subsequent incremental calculator runs maintain the same semantics.

> Forward / 預測相關欄位（`ttm_eps_forward`、`pe_forward`、`predict_target_price`、`upside_pct`、`roe_forward`、`pe_percentile_forward`）已從 `valuation_daily` 移除。
> ML pipeline 的 EPS 成長拆解（`base_eps_growth_pct` / `ml_eps_delta_pct`）在 `strategies/step2_finalize_strategy.py` 用 `predictions_results.csv` 自己算，不經 DB。

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | db | PostgreSQL host |
| `DB_USER` | user | Database user |
| `DB_PASSWORD` | password | Database password |
| `DB_NAME` | stock_db | Database name |
| `DB_PORT` | 5432 | Database port |
| `START_DATE` | - | Used by `calculate_daily.py` for incremental updates. |

---

## Running the Calculators

### Via Dedicated Script (Recommended)
We use a dedicated shell script to run all analytics after the ETL pipeline:
```bash
./schedules/daily_calculator.sh 20260211
```

### Manual Execution

All seven calculators default to **incremental-only**: they auto-detect `MAX(date)` on
the output table and only compute rows with `date > last_processed`. No flags →
idempotent no-op when the DB is already up-to-date.

```bash
# Indicators
docker compose run --rm calculator python calculate_daily.py
# Trust holding
docker compose run --rm calculator python calculate_trust_holding.py
# Dealer holding
docker compose run --rm calculator python calculate_dealer_holding.py
# Shareholding concentration
docker compose run --rm calculator python calculate_shareholding_concentration.py
# Short interest analysis
docker compose run --rm calculator python calculate_short_interest_analysis.py
# Margin pressure analysis
docker compose run --rm calculator python calculate_margin_pressure_analysis.py
# Valuations (PIT expanding rank percentile)
docker compose run --rm calculator python calculate_valuation.py
```

#### `--force-full` flag

Every calculator accepts `--force-full` which drops the output table and recomputes
from scratch. Use after a schema change or bug fix. For `calculate_valuation.py`,
prefer the one-shot `backfill_pit_percentile.py` migration over `--force-full` when
only the percentile semantics need realigning — it updates in place without
recomputing close/TTM.

```bash
docker compose run --rm calculator python calculate_valuation.py --force-full
docker compose run --rm calculator python backfill_pit_percentile.py [--dry-run]
```

#### Env-var overrides

`calculate_daily.py` still respects `START_DATE` / `END_DATE` (YYYYMMDD or YYYY-MM-DD)
to force a specific window — used by the retry flow (`schedules/daily_retry.sh`) when
re-running stale dates. The other six calculators ignore env vars and always pick up
from `MAX(date)` unless `--force-full` is passed.

#### Migration Sequence (fresh DB / schema rebuild)

A fresh clone (or any DB with old-schema tables — e.g. without
`PRIMARY KEY (date, symbol)` or missing streak columns) needs the one-time
rebuild sequence below. `CREATE TABLE IF NOT EXISTS` no-ops on pre-existing
tables, so the old schema won't auto-upgrade:

```bash
# 1. Rebuild image (source not mounted)
docker compose build calculator

# 2. Rebuild all six DROP-replaced tables under the new schema
docker compose run --rm calculator python calculate_daily.py                       --force-full
docker compose run --rm calculator python calculate_dealer_holding.py              --force-full
docker compose run --rm calculator python calculate_trust_holding.py               --force-full
docker compose run --rm calculator python calculate_shareholding_concentration.py  --force-full
docker compose run --rm calculator python calculate_short_interest_analysis.py     --force-full
docker compose run --rm calculator python calculate_margin_pressure_analysis.py    --force-full

# 3. valuation_daily — either rebuild from scratch:
docker compose run --rm calculator python calculate_valuation.py --force-full
#    or, if close/TTM are trusted and only percentile semantics need realigning:
docker compose run --rm calculator python backfill_pit_percentile.py --dry-run
docker compose run --rm calculator python backfill_pit_percentile.py
```

After step 3 all subsequent runs are incremental no-ops until new raw data
arrives. Skip step 2/3 only if you know the DB was already rebuilt under the
current schema.

---

## Database Table Schemas

### technical_indicators
```sql
CREATE TABLE technical_indicators (
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ma5 DOUBLE PRECISION,
    ma10 DOUBLE PRECISION,
    ma20 DOUBLE PRECISION,
    ma60 DOUBLE PRECISION,
    ma120 DOUBLE PRECISION,
    ma240 DOUBLE PRECISION,
    vma5 DOUBLE PRECISION,
    vma10 DOUBLE PRECISION,
    vma20 DOUBLE PRECISION,
    vma60 DOUBLE PRECISION,
    vma120 DOUBLE PRECISION,
    vma240 DOUBLE PRECISION,
    k DOUBLE PRECISION,
    d DOUBLE PRECISION,
    rsi6 DOUBLE PRECISION,
    rsi12 DOUBLE PRECISION,
    macd_dif DOUBLE PRECISION,
    macd_dea DOUBLE PRECISION,
    macd_hist DOUBLE PRECISION,
    bb_upper DOUBLE PRECISION,
    bb_middle DOUBLE PRECISION,
    bb_lower DOUBLE PRECISION,
    foreign_streak_days BIGINT,
    trust_streak_days BIGINT,
    dealer_streak_days BIGINT,
    PRIMARY KEY (date, symbol)
);
```

### valuation_daily
```sql
CREATE TABLE valuation_daily (
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    close DOUBLE PRECISION,
    ttm_eps_official DOUBLE PRECISION,
    pe_official DOUBLE PRECISION,
    pe_percentile_official DOUBLE PRECISION,
    roe_official DOUBLE PRECISION,
    pced_file TEXT,
    pced_row BIGINT,
    pced_col TEXT,
    PRIMARY KEY (date, symbol)
);
```
> `pced_file`/`pced_row`/`pced_col` 是 lineage 欄位，但 valuation_daily 是 calculator 算出來的（非 processor 產出的 CSV），所以填固定常數：`pced_file="calculated_pit"`、`pced_row=0`、`pced_col="x"`。


### Date Type Requirement (Important)
- `technical_indicators.date` must use `TEXT` type (not `DATE`).
- This keeps join/type behavior consistent with `daily_quotes.date` and other core tables, which also store date as text.

Quick checks:
```sql
SELECT data_type
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name='technical_indicators'
  AND column_name='date';
```

If it is not `text`, convert it:
```sql
ALTER TABLE technical_indicators
ALTER COLUMN date TYPE text
USING date::text;
```

## Running the Calculator

### After Initial Data Import
```bash
# Import all daily quotes
START_DATE=20220101 END_DATE=20221231 docker compose run --rm importer

# Calculate indicators
docker compose run --rm calculator
```

### After Daily Updates
```bash
# Daily pipeline
./schedules/daily_update.sh 20260201

# Or manually
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer
docker compose run --rm calculator
```

### Force Recalculate All Indicators
```bash
# Recalculate technical_indicators from scratch (useful after data corrections)
docker compose run --rm calculator python calculate_daily.py --force-full
```

## Performance Considerations

### Processing Time
- **~2000 stocks** × **~500 trading days** = ~1M rows
- Calculation time: ~2-5 minutes (depends on hardware)

### Memory Usage
- Loads entire `daily_quotes` table into memory
- Typical memory usage: 500MB - 1GB

### Optimization Tips
1. **Indexes**: Ensure `idx_daily_quotes_symbol_date` exists for fast data loading
2. **Docker Resources**: Allocate sufficient memory to Docker (recommend 4GB+)
3. **Batch Size**: Calculator processes all stocks in one batch (no partial updates)

## Troubleshooting

### Issue: Calculator runs forever or crashes
- **Solution**: Check Docker memory allocation. Ensure the daemon can use 4GB+.

### Issue: Missing indicator values (NULL) for recent dates
- **Cause**: Indicators require historical data. MA60 needs 60 days of data.
- **Expected behavior**: Early dates will have NULL values for longer-period indicators.

### Issue: Calculator fails with "table does not exist"
- **Solution**: Ensure `daily_quotes` table exists and has data. Run importer first.

### Issue: Calculator exits immediately with error log
- **Expected behavior**: fail-fast mode is enabled.
- Check `error_calculator.log` for root cause and traceback.

### Issue: Indicators seem incorrect or inconsistent
- **Solution**: Recalculate from scratch: `docker compose run --rm calculator`

## Downstream Consumers

| Table | Read by |
|---|---|
| `technical_indicators` | `strategies/step2_finalize_strategy.py` (MA / RSI / MACD / KD features); `backtester/` |
| `shareholding_concentration` | `strategies/step1_prepare_data.py` |
| `valuation_daily` | `strategies/step1_prepare_data.py::fetch_valuation_features` — uses `roe_official` + `pe_percentile_official` |
| `short_interest_analysis`, `margin_pressure_analysis` | `strategies/step1_prepare_data.py` market-sentiment features |

All downstream code connects directly via `common/db.py::get_db_url()`.
