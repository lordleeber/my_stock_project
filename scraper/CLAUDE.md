# Scraper Module Guide

Scraper 已改成與 processor 一致的頻率分層：`daily/`, `weekly/`, `monthly/`, `quarterly/`。

## Entry Points

- `scraper/scraper_daily.py`
- `scraper/scraper_weekly.py`
- `scraper/scraper_monthly.py`
- `scraper/scraper_quarterly.py`

Backward compatibility:
- `scraper/check_daily_outputs.py`, `scraper/check_weekly_outputs.py`, `scraper/check_monthly_outputs.py`, `scraper/check_quarterly_outputs.py` 目前是新分層 checker 的 wrapper。

## Docker Services

`docker-compose.yml` 目前對應：

- `scraper-daily` -> `python scraper/scraper_daily.py`
- `scraper-weekly` -> `python scraper/scraper_weekly.py`
- `scraper-monthly` -> `python scraper/scraper_monthly.py`
- `scraper-quarterly` -> `python scraper/scraper_quarterly.py`

## Folder Layout

- `daily/`
  - `fetch_daily_sii.py`, `fetch_daily_otc.py`: daily 市場資料抓取
  - `fetch_ex_dividend.py`, `fetch_capital_reduction.py`, `fetch_par_value_change.py`: 每日公告資料抓取
  - `check_outputs.py`: daily 輸出完整性檢查

- `weekly/`
  - `fetch_tdcc.py`: TDCC OpenData 單次抓取（使用 `curl`）
  - `fetch_tdcc_history.py`: TDCC 歷史資料抓取
  - `check_outputs.py`: weekly 輸出檢查

- `monthly/`
  - `fetch_monthly_revenue.py`: 月營收抓取
  - `fetch_stock_info.py`, `fetch_stock_tags.py`, `generate_active_stocks.py`: 月度/輔助基礎資料抓取與產生
  - `check_outputs.py`: monthly 輸出檢查

- `quarterly/`
  - `fetch_quarterly_reports.py`: 季報抓取（quarterly_reports + 三大報表 raw）
  - `check_outputs.py`: quarterly 輸出檢查

## Required Env Vars

- Daily
  - `START_DATE`, `END_DATE`（可省略，省略時抓今天）
  - `MARKET_TYPE` (`SII`/`OTC`/`ALL`)

- Weekly
  - optional: `TDCC_DATE`（指定要驗證的週資料日期，YYYYMMDD）
  - `scraper_weekly.py` 固定輸出到 `/app/data/raw/shareholding`

- Monthly
  - required: `REVENUE_YEAR`, `REVENUE_MONTH`

- Quarterly
  - required: `REPORT_YEAR`, `REPORT_QUARTER`

## Raw Output Paths (current)

- Daily categories: `data/raw/<category>/YYYY/YYYYMMDD/{sii,otc}.csv`
- Monthly revenue: `data/raw/monthly_revenue/YYYY/YYYYMXX/market.csv`
- Quarterly reports: `data/raw/quarterly_reports/YYYY/YYYYQX/{sii,otc}.{xls,csv}`
- Quarterly statements:
  - `data/raw/income_statement/YYYY/YYYYQX/{sii,otc}_*.csv`
  - `data/raw/balance_sheet/YYYY/YYYYQX/{sii,otc}_*.csv`
  - `data/raw/cash_flow/YYYY/YYYYQX/{sii,otc}_*.csv`
- Weekly shareholding: `data/raw/shareholding/YYYY/TDCC_OD_1-5_YYYYMMDD.csv`

## Commands

```bash
# daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily

# weekly
docker compose run --rm scraper-weekly

# monthly
REVENUE_YEAR=2026 REVENUE_MONTH=1 docker compose run --rm scraper-monthly

# quarterly
REPORT_YEAR=2025 REPORT_QUARTER=3 docker compose run --rm scraper-quarterly
```

## Notes

- 這次重構目標是「入口與分層一致化」。既有抓取邏輯（TWSE/TPEx/MOPS/TDCC）保持不變。
- 四個入口（daily/weekly/monthly/quarterly）都會在抓取完成後自動執行對應 `check_outputs`。
- `scraper/Dockerfile` 已內建 `curl`（供 `weekly/fetch_tdcc.py` 使用）。
- 如有改程式碼，先重建 image：

```bash
docker compose build scraper-daily scraper-weekly scraper-monthly scraper-quarterly
```
