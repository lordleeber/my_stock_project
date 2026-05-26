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
- **`ttm_eps_official`**: Sum of the 4 most recently published single-quarter EPS (`eps_q`).

### Output Metrics
- **`pe_calculated`**: `close / ttm_eps_official` (computed internally; not persisted to DB).
- **`pe_official`**: 官方 PE（從 `pe_ratio` 直接合併）。
- **`pe_percentile_official`**: **PIT expanding rank** — for each `(symbol, date)` row,
  rank `pe_calculated` against `{same symbol's PE values with date <= row's date}`. Once
  written, a row's percentile is **frozen** (PIT-safe). Implemented via
  `pandas.expanding().rank(pct=True)` over the historical DB tail concatenated with the
  new batch.
- **`roe_official`**: `ttm_eps_official / nav_per_share * 100`.

> **Migration**: `calculator/backfill_pit_percentile.py` is the one-time migration that
> rewrites all historical `pe_percentile_official` rows under the expanding-rank
> semantics. Was run on calc-per-cohort branch as part of Phase 2. Subsequent
> incremental calculator runs maintain the same semantics.

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

---

## Database Table Schemas

### technical_indicators
... (same as before) ...

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
    PRIMARY KEY (date, symbol)
);
```


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
- **Solution**: Check Docker memory allocation. Increase to 4GB+ in Docker Desktop settings.

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
