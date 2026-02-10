# Scraper Module Guide (for AI Assistants)

This guide covers the data scraping component of the Taiwan stock market analysis pipeline.

## Overview

The scraper fetches raw CSV data from Taiwan stock market sources:
- **TWSE** (twse.com.tw) - Taiwan Stock Exchange (SII-listed stocks)
- **TPEx** (tpex.org.tw) - Taipei Exchange (OTC-listed stocks)
- **MOPS** (mopsov.twse.com.tw) - Market Observation Post System (financial reports)
- **TDCC** (tdcc.com.tw) - Taiwan Depository & Clearing Corporation (shareholding data)

## Data Sources & Update Frequency

| Source | Service | What it fetches | Update Frequency |
|--------|---------|----------------|------------------|
| TWSE (twse.com.tw) | `scraper-daily` | Daily quotes, institutional investors, foreign holdings, margin, P/E, indices | Daily (after market close) |
| TPEx (tpex.org.tw) | `scraper-daily` | Same categories for OTC-listed stocks + Index Summary | Daily (after market close) |
| MOPS (mopsov.twse.com.tw) | `scraper-monthly` | Monthly revenue reports | Monthly (before 10th) |
| MOPS (mopsov.twse.com.tw) | `scraper-quarterly` | Quarterly financial reports (SII/OTC), income statement (t163sb04), balance sheet (t163sb05), cash flow (t163sb20) | Quarterly (approx. 45 days after Q-end) |
| TDCC (tdcc.com.tw) | `scraper-weekly` | Shareholding dispersion per stock | Weekly (scraped on Sunday) |

## Output Directory Structure

```
data/raw/                          # Scraper output (original CSVs)
├── daily_quotes/date=YYYYMMDD/{sii,otc}.csv
├── institutional_investors/date=YYYYMMDD/{sii,otc}.csv
├── institutional_summary/date=YYYYMMDD/{sii,otc}.csv
├── foreign_holding/date=YYYYMMDD/{sii,otc}.csv
├── margin_trading/date=YYYYMMDD/{sii,otc}.csv
├── margin_sbl/date=YYYYMMDD/{sii,otc}.csv
├── pe_ratio/date=YYYYMMDD/{sii,otc}.csv
├── monthly_revenue/date=YYYYMM01/market.csv
├── income_statement/date=YYYYQX/{sii,otc}_*.csv
├── balance_sheet/date=YYYYQX/{sii,otc}_*.csv
├── cash_flow/date=YYYYQX/{sii,otc}_*.csv
├── shareholding_div/date=YYYYMMDD/{symbol}.csv   # Per-stock format (2023/09~)
└── shareholding_div2/TDCC_OD_1-5_YYYYMMDD.csv   # All-in-one format (2020/01~2023/09)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `START_DATE` | today | YYYYMMDD format |
| `END_DATE` | today | YYYYMMDD format |
| `MARKET_TYPE` | ALL | SII, OTC, or ALL |
| `FETCH_DELAY` | 3.0 | Seconds between scraper requests |
| `REVENUE_YEAR` | - | For scraper-monthly (AD year) |
| `REVENUE_MONTH` | - | For scraper-monthly |
| `TDCC_DATE` | - | For scraper-weekly (YYYYMMDD) |

## Docker Services

| Service | Command | Purpose |
|---------|---------|---------|
| `scraper-daily` | `python main.py` | Fetch daily market data |
| `scraper-weekly` | `python scraper/generate_active_stocks.py ... && python scraper/fetch_tdcc_history.py -f ... -d $TDCC_DATE` | Generate active stocks from monthly revenue, then fetch TDCC shareholding |
| `scraper-monthly` | `python fetch_monthly_revenue.py --year $REVENUE_YEAR --month $REVENUE_MONTH` | Fetch monthly revenue (requires REVENUE_YEAR, REVENUE_MONTH) |

## Running the Scraper

### Daily Data
```bash
# Fetch daily market data for a specific date
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily

# Fetch a date range
START_DATE=20260201 END_DATE=20260210 docker compose run --rm scraper-daily
```

### Monthly Revenue
```bash
# Fetch a specific month (e.g. 2026/01)
REVENUE_YEAR=2026 REVENUE_MONTH=1 docker compose run --rm scraper-monthly
```

**Important**: Monthly revenue is published before the 10th of each month. Fetching after the 11th ensures completeness.

### Quarterly Financial Reports
```bash
# Fetch 2025 Q3
REPORT_YEAR=2025 REPORT_QUARTER=3 docker compose run --rm scraper-quarterly
```

### TDCC Shareholding Data

#### Using Docker (Recommended)
The weekly update script is automated via launchctl (see Automation section below).

#### Manual Steps (if not using Docker)
```bash
# Step 1: Generate active stock list from latest monthly revenue (data/raw/monthly_revenue)
python scraper/generate_active_stocks.py  # outputs active_stocks.txt
# Or pick a specific month (YYYYMMDD = 1st day of month dir)
python scraper/generate_active_stocks.py --date 20251201

# Step 2: Query available dates from TDCC
python scraper/fetch_tdcc_history.py --list-dates

# Step 3: Fetch data for specific date
python scraper/fetch_tdcc_history.py -f active_stocks.txt -d 20250321
```

## Important Behaviors

### Rate Limiting
- **Standard APIs**: Scraper waits 3 seconds between requests (controlled by `FETCH_DELAY`)
- **TDCC**: Uses random 1-2s delays to avoid overloading their server

### Encoding
- Raw CSVs from TWSE/TPEx are Big5 encoding
- Scraper converts to **UTF-8-sig** for downstream processing

### Taiwan Calendar
- Uses `pandas_market_calendars` (XTAI) to determine trading days
- Automatically skips weekends and national holidays

### ROC Year Conversion
- MOPS uses 民國 (ROC) year format (AD year - 1911)
- Scraper handles automatic conversion to AD year

### Daily Schedule Timing (21:00)
- TWSE publishes most data immediately after market close (~14:30)
- **Foreign holding data (`foreign_holding`) is published with delay** - typically available after 20:00
- Daily schedule set to 21:00 ensures all data (including foreign_holding) is available
- If scraper runs too early, foreign_holding files will only contain headers (no data rows)

### TDCC Scraper Features
- **Auto CSRF token management**: Parses and renews session tokens automatically
- **Checkpoint resume**: Skips existing .csv files, safe to re-run on failure
- **`--no-verify` flag**: For SSL certificate issues

## Automation Schedules (launchctl)

| Schedule | Plist | Script | Time |
|----------|-------|--------|------|
| Daily quotes | `com.poyilee.stock-daily-update` | StockDailyUpdate.app | Every day 21:00 |
| Weekly TDCC | `com.poyilee.stock-weekly-update` | `scripts/weekly_tdcc_update.sh` | Every Sunday 13:15 |
| Monthly revenue | `com.poyilee.stock-monthly-update` | `scripts/monthly_revenue_update.sh` | Every 12th 17:00 |

All plist files are in `~/Library/LaunchAgents/`. Manage with:
```bash
launchctl load ~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist
launchctl unload ~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist
launchctl list | grep poyilee  # verify loaded
```

## Troubleshooting

### Issue: Foreign holding data only has headers
- **Cause**: Scraper ran before 20:00 when data is not yet published
- **Solution**: Wait until after 20:00 and re-run scraper for that date

### Issue: TDCC fetch fails with SSL errors
- **Solution**: Use the `--no-verify` flag: `python scraper/fetch_tdcc_history.py --no-verify -f active_stocks.txt -d 20250321`

### Issue: Scraper gets blocked or rate-limited
- **Solution**: Increase `FETCH_DELAY` environment variable (default is 3 seconds)

### Issue: Monthly revenue data incomplete
- **Solution**: Verify you're fetching after the 11th of the month when all data is published

## Next Steps

After scraping, data flows to:
1. **Processor** (`processor/CLAUDE.md`) - Cleans and standardizes raw CSVs
2. **Importer** (`importer/CLAUDE.md`) - Loads processed data into PostgreSQL
3. **Calculator** (`calculator/CLAUDE.md`) - Computes technical indicators
