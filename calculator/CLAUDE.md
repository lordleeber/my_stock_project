# Calculator Module Guide (for AI Assistants)

This guide covers the technical indicator calculation component of the Taiwan stock market analysis pipeline.

## Overview

The calculator component refines raw market and financial data into actionable investment insights. It consists of two main pillars:

1.  **Technical Indicators (`calculate_daily.py`)**: Computes MA, RSI, MACD, etc., for price trend analysis.
2.  **Forward Valuation (`calculate_valuation.py`)**: Computes PIT-accurate TTM EPS, Forward PE, Target Prices, and ROE for valuation analysis.

Error handling is fail-fast:
- Any runtime error writes to `/error_calculator.log` or `/error_valuation_calculator.log`
- Exits immediately with non-zero status.

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

## Forward Valuation (`calculate_valuation.py`)

This is the "Brain" of the valuation system. it integrates Price, Financial Reports, and ML Predictions using **Point-in-Time (PIT)** logic.

### Core Logic: Point-in-Time (PIT) Alignment
To avoid look-ahead bias, the calculator anchors financial data to their **official publication deadlines**:
- Q1: May 15 | Q2: Aug 14 | Q3: Nov 14 | Q4: Mar 31.
Every daily valuation record uses the latest report *available at that specific date*.

### Dual TTM EPS Calculation
- **`ttm_eps_official`**: Sum of the 4 most recently published single-quarter EPS (`eps_q`).
- **`ttm_eps_forward`**: Sum of the 3 most recently published quarters + **1 predicted quarter** from `eps_predictions`.
- **The Swap**: As time passes, the oldest quarter is dropped and replaced by the ML prediction for the upcoming quarter.

### Forward Metrics
- **`pe_forward`**: `close / ttm_eps_forward`.
- **`predict_target_price`**: `ttm_eps_forward * pe_official`.
- **`upside_pct`**: Potential return based on the valuation surprise.
- **`pe_percentile_forward`**: Historical rank of the current price against the *predicted* future earnings.

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
```bash
# Indicators
docker compose run --rm calculator python calculate_daily.py
# Valuations (Recomputes full history to ensure percentile consistency)
docker compose run --rm calculator python calculate_valuation.py
```

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
    ttm_eps_forward DOUBLE PRECISION,
    pe_official DOUBLE PRECISION,
    pe_forward DOUBLE PRECISION,
    pe_percentile_official DOUBLE PRECISION,
    pe_percentile_forward DOUBLE PRECISION,
    predict_target_price DOUBLE PRECISION,
    upside_pct DOUBLE PRECISION,
    roe_official DOUBLE PRECISION,
    roe_forward DOUBLE PRECISION,
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
# Recalculate from scratch (useful after data corrections)
docker compose run --rm calculator
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

### Issue: Indicators not appearing in backend API
- **Solution**: Verify `technical_indicators` table has data:
  ```bash
  docker compose exec -T db psql -U user -d stock_db -c "SELECT COUNT(*) FROM technical_indicators;"
  ```

### Issue: Calculator fails with "table does not exist"
- **Solution**: Ensure `daily_quotes` table exists and has data. Run importer first.

### Issue: Calculator exits immediately with error log
- **Expected behavior**: fail-fast mode is enabled.
- Check `error_calculator.log` for root cause and traceback.

### Issue: Indicators seem incorrect or inconsistent
- **Solution**: Recalculate from scratch: `docker compose run --rm calculator`

## Integration with Backend API

The calculator populates data used by these backend endpoints:

### Scanner Endpoints
- `/scanner/volume-spike` - Uses MA60, MA5, MA10, MA20, KD, RSI, MACD
- `/scanner/candlestick/{symbol}` - Returns MA5, MA10, MA20, MA60

### Analysis Endpoints
- `/analysis/ma` - Returns MA5, MA10, MA20, MA60, MA120, MA240
- `/analysis/vma` - Returns VMA5, VMA10, VMA20, VMA60

### ML Training Data
- `/ml/training-data` - Returns all indicators when `include_indicators=true`

## Next Steps

After calculation, data is ready for:
- **Backend API** (`backend/CLAUDE.md`) - Serves data to frontend
- **Frontend** (`frontend/CLAUDE.md`) - Displays charts and analysis
