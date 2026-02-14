# Calculator Module Guide (for AI Assistants)

This guide covers the technical indicator calculation component of the Taiwan stock market analysis pipeline.

## Overview

The calculator computes technical indicators from `daily_quotes` and stores results in `technical_indicators`.
Entry point:
- `calculate_daily.py`

Error handling is fail-fast:
- Any runtime error writes to `/error_calculator.log`
- Then exits immediately with non-zero status

The core calculation logic is integrated in `calculate_daily.py`.

Indicators:
- Moving averages (MA, VMA)
- Momentum indicators (KD, RSI)
- Trend indicators (MACD)
- Volatility indicators (Bollinger Bands)

**Input**: `daily_quotes` table in PostgreSQL
**Output**: `technical_indicators` table in PostgreSQL

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | db | PostgreSQL host |
| `DB_USER` | user | Database user |
| `DB_PASSWORD` | password | Database password |
| `DB_NAME` | stock_db | Database name |
| `DB_PORT` | 5432 | Database port |
| `START_DATE` | - | Incremental start date (`YYYYMMDD` or `YYYY-MM-DD`) |
| `END_DATE` | - | Incremental end date (`YYYYMMDD` or `YYYY-MM-DD`) |

## Docker Service

```bash
# Daily entry (default for calculator service)
docker compose run --rm calculator
docker compose run --rm calculator python calculate_daily.py

# Rebuild after code changes
docker compose build calculator
```

**Important**:
- `calculate_daily.py` supports full mode (no `START_DATE`) and incremental mode (with `START_DATE`).

## Technical Indicators

Computed for every stock, stored in `technical_indicators` table.

### Moving Averages (MA)
- **Periods**: 5, 10, 20, 60, 120, 240 days
- **Formula**: Simple Moving Average (SMA) of closing prices
- **Columns**: `ma5`, `ma10`, `ma20`, `ma60`, `ma120`, `ma240`

### Volume Moving Averages (VMA)
- **Periods**: 5, 10, 20, 60, 120, 240 days
- **Formula**: Simple Moving Average (SMA) of volume
- **Columns**: `vma5`, `vma10`, `vma20`, `vma60`, `vma120`, `vma240`

### KD Stochastic Oscillator
- **Period**: 9 days
- **Smoothing**: α=1/3 (exponential smoothing)
- **Formula**:
  - RSV = (Close - Low9) / (High9 - Low9) × 100
  - K = Previous K × 2/3 + RSV × 1/3
  - D = Previous D × 2/3 + K × 1/3
- **Columns**: `k`, `d`
- **Range**: 0-100
- **Interpretation**:
  - K > 80: Overbought
  - K < 20: Oversold
  - K crosses above D: Buy signal
  - K crosses below D: Sell signal

### RSI (Relative Strength Index)
- **Periods**: 6-day and 12-day
- **Formula**: RSI = 100 - (100 / (1 + RS))
  - RS = Average Gain / Average Loss
- **Columns**: `rsi6`, `rsi12`
- **Range**: 0-100
- **Interpretation**:
  - RSI > 70: Overbought
  - RSI < 30: Oversold

### MACD (Moving Average Convergence Divergence)
- **DIF (Fast Line)**: EMA12 - EMA26
- **DEA (Signal Line)**: EMA9 of DIF
- **Histogram**: DIF - DEA (not stored separately)
- **Columns**: `macd_dif`, `macd_dea`
- **Interpretation**:
  - DIF crosses above DEA: Buy signal
  - DIF crosses below DEA: Sell signal
  - Histogram > 0: Bullish momentum
  - Histogram < 0: Bearish momentum

### Bollinger Bands
- **Period**: 20 days
- **Standard Deviation**: 2σ
- **Formula**:
  - Middle Band: MA20
  - Upper Band: MA20 + 2σ
  - Lower Band: MA20 - 2σ
- **Columns**: `bb_upper`, `bb_middle`, `bb_lower`
- **Interpretation**:
  - Price near upper band: Overbought
  - Price near lower band: Oversold
  - Band width expansion: Increased volatility
  - Band width contraction: Decreased volatility

## Implementation Details

### Pandas Vectorized Operations
Uses Pandas with grouped apply (by symbol) for efficiency:
```python
df.groupby('symbol').apply(lambda group: calculate_indicators(group))
```

This approach:
- Processes each stock independently
- Preserves time-series order within each stock
- Leverages Pandas' optimized C extensions

### Database Strategy
1. Fetch `daily_quotes` (with buffer window in incremental mode)
2. Calculate indicators grouped by `symbol`
3. Write to `technical_indicators`
4. Incremental mode deletes target date range first, then inserts recalculated rows

## Database Table Schema

### technical_indicators table
```sql
CREATE TABLE technical_indicators (
    date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT,
    -- Moving Averages
    ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL, ma120 REAL, ma240 REAL,
    -- Volume Moving Averages
    vma5 REAL, vma10 REAL, vma20 REAL, vma60 REAL, vma120 REAL, vma240 REAL,
    -- KD Oscillator
    k REAL, d REAL,
    -- RSI
    rsi6 REAL, rsi12 REAL,
    -- MACD
    macd_dif REAL, macd_dea REAL,
    -- Bollinger Bands
    bb_upper REAL, bb_middle REAL, bb_lower REAL,
    PRIMARY KEY (date, symbol)
);

CREATE INDEX idx_tech_symbol_date ON technical_indicators(symbol, date);
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
