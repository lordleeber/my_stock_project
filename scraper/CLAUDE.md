# Scraper Module Guide

Scraper 已改成與 processor 一致的頻率分層：`daily/`, `weekly/`, `monthly/`, `quarterly/`。

## Entry Points

- `scraper/scraper_daily.py`
- `scraper/scraper_weekly.py`
- `scraper/scraper_monthly.py`
- 季報：**沒有頂層 orchestrator**。`scraper-quarterly` service 沒有預設 command，callers 須直接指定 `python3 scraper/quarterly/fetch_xbrl.py --year ... --quarter ...`（一般經由 `schedules/xbrl_scrape_daily.sh`）。

Backward compatibility:
- `scraper/check_daily_outputs.py`, `scraper/check_weekly_outputs.py`, `scraper/check_monthly_outputs.py` 目前是新分層 checker 的 wrapper。
- 舊的季報抓取（`scraper/scraper_quarterly.py`、`scraper/check_quarterly_outputs.py`、`scraper/quarterly/fetch_quarterly_reports.py`、`scraper/quarterly/check_outputs.py`）已 deprecated，移到 `scraper/_deprecated/` 與 `scraper/quarterly/_deprecated/`。

### 🔴 STRICT IMAGE REBUILD RULE (CORE MANDATE)

`scraper` services (daily, weekly, monthly, quarterly) do not mount source code into `/app`. After any code change in `scraper/` or `common/`, you **MUST** rebuild before running:

```bash
docker compose build scraper-daily scraper-weekly scraper-monthly scraper-quarterly
```

If you skip rebuild, container runtime may execute stale code even when host files look updated.

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
  - `fetch_xbrl.py`: 季報 XBRL 抓取（MOPS XBRL HTML），輸出到 `data/raw/xbrl/YYYY/YYYYQX/`
  - `_deprecated/`: 已停用的舊版季報抓取（`fetch_quarterly_reports.py`、`check_outputs.py`）

## Required Env Vars

- Daily
  - `START_DATE`, `END_DATE`（可省略，省略時抓今天）
  - `MARKET_TYPE` (`SII`/`OTC`/`ALL`)

- Weekly
  - optional: `TDCC_DATE`（指定要驗證的週資料日期，YYYYMMDD）
  - `scraper_weekly.py` 固定輸出到 `/app/data/raw/shareholding`

- Monthly
  - required: `REVENUE_YEAR`, `REVENUE_MONTH`

- Quarterly XBRL
  - 由 `fetch_xbrl.py` 直接吃 `--year` / `--quarter` 參數（不再使用 `REPORT_YEAR`/`REPORT_QUARTER` 環境變數）。一般透過 `schedules/xbrl_scrape_daily.sh` 觸發。

## Raw Output Paths (current)

- Daily categories: `data/raw/<category>/YYYY/YYYYMMDD/{sii,otc}.csv`
- Monthly revenue:
  - snapshot: `data/raw/monthly_revenue/YYYY/YYYYMXX/tmp.csv` (overwritten each run)
  - cumulative: `data/raw/monthly_revenue/YYYY/YYYYMXX/market.csv` (append only newly published rows)
- Quarterly XBRL: `data/raw/xbrl/YYYY/YYYYQX/YYYYQX_<symbol>_YYYYMMDD.html`（flat：每檔直接寫入季別目錄，無 per-symbol 子目錄）

> Legacy raw paths（不再寫入，僅作 archive）: `data/raw/quarterly_reports/`、`data/raw/income_statement/`、`data/raw/balance_sheet/`、`data/raw/cash_flow/`
- Weekly shareholding: `data/raw/shareholding/YYYY/TDCC_OD_1-5_YYYYMMDD.csv`

## Commands

```bash
# daily
START_DATE=20260201 END_DATE=20260201 docker compose run --rm scraper-daily

# weekly
docker compose run --rm scraper-weekly

# monthly
REVENUE_YEAR=2026 REVENUE_MONTH=1 docker compose run --rm scraper-monthly

# quarterly XBRL（一般用 schedules/xbrl_scrape_daily.sh，下面是直接呼叫的 fallback）
docker compose run --rm scraper-quarterly \
    python3 scraper/quarterly/fetch_xbrl.py --year 2025 --quarter 4
```

## Notes

- 這次重構目標是「入口與分層一致化」。既有抓取邏輯（TWSE/TPEx/MOPS/TDCC）保持不變。
- daily/weekly/monthly 入口會在抓取完成後自動執行對應 `check_outputs`；quarterly XBRL 目前沒有 check_outputs（後續可補）。
- `daily/check_outputs.py` 偵測到 missing raw 檔時：寫入 `error_scraper.log` 並讓 `scraper_daily.py` 回傳 `exit 1`，讓 `daily_update.sh` 因 `set -e` 中斷，觸發後續 retry。**不再靜默通過**（避免 TWSE 暫時回 empty 時整條 pipeline 假成功而落漏資料）。
- `monthly/check_outputs.py` 目前會同時檢查 `tmp.csv` 與 `market.csv`。
- `fetch_monthly_revenue.py` 會把每次抓到的 `tmp.csv` 逐筆合併到 `market.csv`，並寫入 `publish_time`（預設當天 `YYYYMMDD`，可由 `PUBLISH_TIME` 覆寫）。
- `scraper/Dockerfile` 已內建 `curl`（供 `weekly/fetch_tdcc.py` 使用）。
- `fetch_xbrl.py` 用**正向驗證**決定能不能存檔（`validate_report()`）：回應必須 ≥ 100 KB 且帶 XBRL namespace（`xbrl.org/2003/instance` 或 `2013/inlineXBRL`），否則一律視為失敗。門檻是 2026-08-01 對 `data/raw/xbrl` 全量 41,158 檔校準出來的——最小的正常報表 351 KB、沒有任何一份 < 200 KB，而 MOPS 的安全性阻擋頁 800 bytes、「檔案不存在!」97 bytes。
  - 之所以不是逐條列舉錯誤頁字樣：舊版就是這樣做，兩個 marker 各差一個字（`the`/`this`、`執行`/`呈現`），2026Q2 因此存進 1,805 個阻擋頁。要改判斷條件請維持正向驗證的形式，不要退回窮舉錯誤訊息。
  - `classify_failure_reason()` 只負責把失敗原因寫清楚（`rate_limit` / `page_not_accessible` / `report_not_published`），漏判不會讓壞資料落地。
  - `load_existing_report_names()` 只把**通過驗證**的檔案列入 dedupe key，所以存壞的檔案下次執行會自動重抓，不會像舊版那樣錯一次就永遠 SKIP。
  - 申報期限前來抓會大量收到 `report_not_published`（例如 8/14 前抓 Q2），這是正常的，等排程逐日補齊即可。
