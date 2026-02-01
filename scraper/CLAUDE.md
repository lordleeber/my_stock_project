# Data Pipeline Guide (for AI Assistants)

This document covers the **entire data pipeline**: scraper → processor → importer → calculator.
All components live in the project root under their respective directories.

## Architecture Overview

```
scraper/     → Fetch raw CSV from TWSE/TPEx/MOPS/TDCC
processor/   → Clean & standardize (Chinese→English columns, numeric conversion)
importer/    → Load into PostgreSQL (delete-before-insert, dedup by date+market)
calculator/  → Compute technical indicators (MA, KD, RSI, MACD, Bollinger)
scripts/     → Orchestration (daily_update.sh)
common/      → Shared constants (CATEGORY_MAP)
```

## Daily Update Pipeline

```bash
# Run full pipeline for a specific date
./scripts/daily_update.sh 20260201

# Or run each step manually via Docker
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor
START_DATE=20260201 END_DATE=20260201 docker compose run --rm processor python convert_institutional_summary.py
START_DATE=20260201 END_DATE=20260201 docker compose run --rm importer
START_DATE=20260201 END_DATE=20260201 docker compose run --rm calculator
```

Pipeline order matters: scraper → processor → importer → calculator.

## Data Sources

| Source | Service | What it fetches |
|--------|---------|----------------|
| TWSE (twse.com.tw) | `scraper-daily` | Daily quotes, institutional investors, foreign holdings, margin, P/E |
| TPEx (tpex.org.tw) | `scraper-daily` | Same categories for OTC-listed stocks |
| MOPS (mopsov.twse.com.tw) | `scraper-monthly` | Monthly revenue reports |
| TDCC (tdcc.com.tw) | `scraper-weekly` | Shareholding dispersion per stock |

## Directory Structure (Data)

```
data/
├── raw/                          # Scraper output (original CSVs)
│   ├── daily_quotes/date=YYYYMMDD/{sii,otc}.csv
│   ├── institutional_investors/date=YYYYMMDD/{sii,otc}.csv
│   ├── institutional_summary/date=YYYYMMDD/{sii,otc}.csv
│   ├── foreign_holding/date=YYYYMMDD/{sii,otc}.csv
│   ├── margin_trading/date=YYYYMMDD/{sii,otc}.csv
│   ├── margin_sbl/date=YYYYMMDD/{sii,otc}.csv
│   ├── pe_ratio/date=YYYYMMDD/{sii,otc}.csv
│   ├── monthly_revenue/date=YYYYMM01/market.csv
│   └── shareholding_div/date=YYYYMMDD/{symbol}.csv
├── processed/                    # Processor output (cleaned CSVs)
│   └── (same structure, standardized schemas)
└── postgres/                     # PostgreSQL data volume
```

## Environment Variables

All services use these:

| Variable | Default | Description |
|----------|---------|-------------|
| `START_DATE` | today | YYYYMMDD format |
| `END_DATE` | today | YYYYMMDD format |
| `MARKET_TYPE` | ALL | SII, OTC, or ALL |
| `FETCH_DELAY` | 3.0 | Seconds between scraper requests |
| `FORCE_REIMPORT` | 0 | Set to 1 to overwrite existing DB data |
| `IMPORT_CATEGORY` | (all) | Import only a specific category |
| `REVENUE_YEAR` | - | For scraper-monthly (AD year) |
| `REVENUE_MONTH` | - | For scraper-monthly |
| `TDCC_DATE` | - | For scraper-weekly (YYYYMMDD) |

Database (used by importer, calculator, backend):

| Variable | Default |
|----------|---------|
| `DB_HOST` | db |
| `DB_USER` | user |
| `DB_PASSWORD` | password |
| `DB_NAME` | stock_db |
| `DB_PORT` | 5432 |

## Key Database Tables

| Table | Key columns | Source |
|-------|------------|--------|
| `daily_quotes` | date, symbol, open, high, low, close, volume | TWSE/TPEx daily |
| `technical_indicators` | date, symbol, ma5..ma240, k, d, rsi6, rsi12, macd_dif, macd_dea | Calculated |
| `institutional_investors` | date, symbol, foreign_net, trust_net, dealer_net | TWSE/TPEx T86 |
| `foreign_holding` | date, symbol, foreign_held_shares, foreign_held_ratio | TWSE/TPEx QFIIS |
| `margin_trading` | date, symbol, margin_long_balance, margin_short_balance | TWSE/TPEx |
| `monthly_revenue` | date, symbol, revenue, yoy_pct | MOPS |
| `shareholding_div` | date, symbol, level, holders, shares | TDCC |
| `market_indices` | date, symbol, close, change | Extracted from daily_quotes |

## Processor Column Mapping

The processor converts Chinese column names to English. Key mappings in `processor/schemas.py`:

- 證券代號 → symbol
- 成交股數 → volume
- 開盤價 → open / 收盤價 → close / 最高價 → high / 最低價 → low
- 外陸資買賣超股數 → foreign_net
- 投信買賣超股數 → trust_net

## Calculator: Technical Indicators

Computed for every stock, stored in `technical_indicators` table:

- **MA**: 5, 10, 20, 60, 120, 240-day moving averages
- **VMA**: Volume moving averages (same periods)
- **KD**: Stochastic oscillator (9-period RSV, smoothing α=1/3)
- **RSI**: 6-period and 12-period
- **MACD**: DIF (EMA12-EMA26), DEA (EMA9 of DIF), histogram
- **Bollinger Bands**: MA20 ± 2σ

## Important Behaviors

1. **Incremental by default**: Each stage skips existing data. Use `FORCE_REIMPORT=1` for importer override.
2. **Encoding**: Raw CSVs from TWSE/TPEx are Big5 → converted to UTF-8-sig by scraper.
3. **ETF filtering**: Importer excludes symbols starting with "00" (ETFs).
4. **OHLCV validation**: Importer filters rows where all of open/high/low/close/volume are NULL or 0.
5. **Rate limiting**: Scraper waits 3 seconds between requests. TDCC uses random 1-2s delays.
6. **Taiwan calendar**: Uses `pandas_market_calendars` (XTAI) to determine trading days.
7. **ROC year**: MOPS uses 民國 year (AD year - 1911). Scraper handles conversion.

## Common Tasks

### Batch import historical data
```bash
# Process + import a full year
for date in $(python3 -c "
import pandas_market_calendars as mcal
cal = mcal.get_calendar('XTAI')
for d in cal.schedule('2022-01-01','2022-12-31').index:
    print(d.strftime('%Y%m%d'))
"); do
  START_DATE=$date END_DATE=$date docker compose run --rm processor
  START_DATE=$date END_DATE=$date docker compose run --rm processor python convert_institutional_summary.py
  START_DATE=$date END_DATE=$date docker compose run --rm importer
done
# Then recalculate all indicators
docker compose run --rm calculator
```

### Force recalculate all technical indicators
```bash
docker compose run --rm calculator
```

### Import only one category
```bash
docker compose run --rm -e IMPORT_CATEGORY=monthly_revenue importer
```

## Docker Services Reference

| Service | Command | Purpose |
|---------|---------|---------|
| `scraper-daily` | `python main.py` | Fetch daily market data |
| `scraper-weekly` | `python fetch_tdcc_history.py` | Fetch TDCC shareholding |
| `scraper-monthly` | `python fetch_monthly_revenue.py` | Fetch monthly revenue |
| `processor` | `python convert.py` | Process daily data |
| `importer` | `python main.py` | Load CSVs into PostgreSQL |
| `calculator` | `python main.py` | Compute technical indicators |
| `db` | postgres:15 | PostgreSQL database |
| `backend` | uvicorn | FastAPI server (port 8000) |
| `frontend` | next start | Next.js UI (port 3000) |
