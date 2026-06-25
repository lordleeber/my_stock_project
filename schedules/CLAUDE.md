# Schedules Guide

這個目錄裝 **cross-platform** 的 shell script（業務邏輯層），不綁特定 OS。

實際的時間排程（誰在什麼時候呼叫這些 .sh）由各 OS 的目錄負責：

- **Ubuntu**：`schedules_ubuntu/`（systemd `.timer` + `.service`） — 生產環境
- **macOS**：`schedules_macos/`（launchd `.plist`） — 已 deprecated，僅作 archive

shell script 內容與 OS 無關，兩邊都能直接 invoke。

## Available Scripts

- `schedules/daily_update.sh`
  - 流程：`scraper-daily -> processor -> audit -> importer -> calculator`
  - 參數：可選 `YYYYMMDD`（不給則用今天）
  - calculator 實際執行：`calculate_daily.py -> calculate_trust_holding.py -> calculate_dealer_holding.py -> calculate_shareholding_concentration.py -> calculate_short_interest_analysis.py -> calculate_margin_pressure_analysis.py -> calculate_valuation.py`
  - 透傳 `FORCE_REPROCESS` / `FORCE_REIMPORT` 給 processor / audit / importer container（給 retry 在偵測到 stale 狀態時使用）

- `schedules/weekly_update.sh`
  - 流程：`scraper-weekly -> processor(convert_weekly) -> importer(shareholding) -> processor(convert_dividend) -> importer(import_dividend)`
  - 自動偵測最新 TDCC 檔案日期後處理（shareholding 段）
  - 末段順帶處理除權息（dividend）：除權息 raw 由每日 `scraper-daily` 持續累積，這裡只需 process + import。
    - `convert_dividend.py` 預設只重算**當年度**；`import_dividend.py` 預設只對**當年度** delete-before-insert（不 drop 整表）。過去年度視為 immutable 不重算/重匯。
    - 首次 bootstrap 或補歷史：對這兩支帶 `DIVIDEND_FULL=1`（processor 重算所有年度、importer 全量 replace 整表）。

- `schedules/monthly_update.sh`
  - 目標月份：自動抓「上個月」
  - 只在每月 1~15 日執行（公告窗口），其餘日期直接 skip
  - 流程：`scraper-monthly -> (day 15 only) generate_active_stocks -> processor(convert_monthly) -> importer(monthly_revenue, FORCE_REIMPORT=1)`

- `schedules/daily_retry.sh`
  - 檢查前一天的 daily_update 是否成功，失敗才重跑
  - 參數：可選 `YYYYMMDD`（不給則用昨天）
  - 判斷邏輯（三層完整性檢查，全綠才 skip）：
    1. **log**：`logs/daily_update_<target_date>_*.log` 是否含 `Daily Stock Data Update Completed`
    2. **raw**：7 個 both-market category（`daily_quotes` / `institutional_summary` / `institutional_investors` / `foreign_holding` / `margin_trading` / `margin_sbl` / `pe_ratio`）× `{sii,otc}` + `market_indices`（otc-only）raw 檔是否存在且非 0 byte
    3. **DB**：8 個 daily 表（`daily_quotes` / `institutional_investors` / `foreign_holding` / `margin_trading` / `margin_sbl` / `pe_ratio` / `institutional_summary` / `margin_summary`）× `{sii,otc}` 該日是否都有資料
       - 兩層的表集合刻意不同：DB 層比 raw 層多了 `margin_summary`（DB-only，無對應 raw 檔層級檢查）、少了 `market_indices`（raw-only）
       - `market_indices` 已每日入庫（sii+otc）但刻意不納入此 retry gate（DB 檢查只按 `date`+`market` 數列數、不看 symbol 內容），純為維持既有觸發條件不變；含 `market_indices` 在內的逐日完整性檢查見 `tools/check_db_completeness.py`
  - 修復路徑：
    - 非交易日（log 含 `No valid trading days`）→ skip
    - raw 缺 → 一般重跑（scraper 會補抓）
    - raw OK 但 DB 缺 → 設 `FORCE_REPROCESS=1` + `FORCE_REIMPORT=1` 讓 processor 重建 stale `processed/all.csv`、importer 覆寫 DB
    - log 沒成功 → 一般重跑全部
  - Ubuntu 端在 03:00 觸發一次（`schedules_ubuntu/stock-daily-retry.timer` 單一 `OnCalendar`）

- `schedules/xbrl_scrape_daily.sh`
  - 流程：只跑 `scraper-quarterly python3 scraper/quarterly/fetch_xbrl.py`
  - 用途：公告期內每天累積 raw XBRL；**不入庫**
  - 參數：可選 `YYYYMMDD` 或 `YYYYQX`
  - 規則（不傳參數時，用今天日期判斷）：
    - `02/01~03/31`：抓「前一年 Q4」
    - `04/01~05/15`：抓「同年 Q1」
    - `07/01~08/15`：抓「同年 Q2」
    - `10/01~11/15`：抓「同年 Q3」
    - 其他日期：直接 skip
  - 透傳 `FORCE_REPROCESS` 給 scraper container

- `schedules/xbrl_process_import.sh` _（手動觸發）_
  - 流程：`processor(convert_quarterly_xbrl) -> importer(import_xbrl) -> importer(import_quarterly_xbrl)`
  - 寫入 DB：`balance_sheet_xbrl` / `income_statement_xbrl` / `cash_flow_xbrl` / `xbrl_codebook` / `quarterly_reports_xbrl`
  - 前提：raw XBRL 已存在（由 `xbrl_scrape_daily.sh` 累積，或手動跑 fetch_xbrl.py）
  - 參數：可選 `YYYYMMDD` 或 `YYYYQX`；窗口外不再 silent skip，會 error 提示改傳 `YYYYQX`
  - 用途：公告期末把累積的 raw 一次入庫；或補單季資料
  - 透傳 `FORCE_REPROCESS` / `FORCE_REIMPORT` 給 processor / importer container

- `schedules/backfill_xbrl.sh`
  - 範圍補齊（多季）。**目前只跑 scrape 階段**（不含 processor/importer）；補完後可對每季呼叫 `xbrl_process_import.sh`，或一次跑 processor + 兩個 importer。

- `schedules/playbook_run.sh`
  - 流程：每月 ML playbook — `train_eps/run_pipeline.py -> strategies/step1~step5 -> backtester/run_rolling.py`
  - 參數：可選 `YYYY-MM-DD`（force run 指定 playbook date）；不給則用今天判斷
  - self-gate：只在當月的 canonical playbook date（cutoff +1：5/8/11 月 = 16 號，其餘 = 11 號；見 `train_eps/shared_config.py::playbook_run_date`）實際執行，非該日直接 exit 0
  - Ubuntu 端由 `stock-playbook-run.timer` 在每月 11 號與 16 號 04:00 觸發（兩個觸發點交給 script self-gate 收斂到正確那天）

- `schedules/_deprecated/quarterly_update.sh`
  - 已停用。原本流程是 `scraper-quarterly -> processor(convert_quarterly) -> importer(import_quarterly)`，餵的是 legacy 季報表。改用 `xbrl_scrape_daily.sh` + `xbrl_process_import.sh`。

## Logging

- 腳本都會將執行結果寫到 `logs/`，格式統一為 `<script>_<TARGET>_<EXEC_DATE>_<EXEC_TIME>.log`：
  - `daily_update_<TARGET_DATE>_<EXEC_DATE>_<EXEC_TIME>.log`（例：`daily_update_20260416_20260417_020000.log`）
  - `daily_retry_<TARGET_DATE>_<EXEC_DATE>_<EXEC_TIME>.log`
  - `weekly_update_<TARGET_DATE>_<EXEC_TS>.log`
  - `monthly_update_<YYYYMM>_<EXEC_TS>.log`（例：`monthly_update_202603_20260410_224500.log`）
  - `xbrl_scrape_<YYYYQX>_<EXEC_TS>.log` / `xbrl_scrape_skip_<EXEC_TS>.log`（每日 scrape；視窗外時 skip）
  - `xbrl_process_import_<YYYYQX>_<EXEC_TS>.log`（手動 process+import）

## Common Commands

```bash
# 手動執行 daily（指定日期）
./schedules/daily_update.sh 20260214

# 手動執行 weekly
./schedules/weekly_update.sh

# 手動執行 monthly
./schedules/monthly_update.sh

# 手動執行 XBRL daily scrape（以今天判斷）
./schedules/xbrl_scrape_daily.sh

# 手動執行 XBRL process+import（公告期末/補資料；前提 raw 已存在）
./schedules/xbrl_process_import.sh
./schedules/xbrl_process_import.sh 2025Q4    # 直接指定季度
```

## OS-Specific 排程操作

- Ubuntu (systemd)：`schedules_ubuntu/CLAUDE.md`
- macOS (launchd)：`schedules_macos/CLAUDE.md`（已 deprecated）

## Notes

- 執行腳本前請確認 Docker Desktop / Docker Engine 已啟動。
- 若有改 Dockerfile/程式碼，請先重建相關 service image。
- 月腳本僅在每月 15 號更新專案根目錄的 `active_stocks.txt`。
- Daily/Weekly/Monthly 寫入對應 `logs/*_update_*.log`；XBRL daily scrape 寫入 `logs/xbrl_scrape_*.log`，手動 process+import 寫入 `logs/xbrl_process_import_*.log`。
