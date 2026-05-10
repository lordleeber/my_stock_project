# Schedules Guide

這份文件描述 `schedules/` 目錄目前的自動化腳本與排程方式。

## Available Scripts

- `schedules/daily_update.sh`
  - 流程：`scraper-daily -> processor -> audit -> importer -> calculator`
  - 參數：可選 `YYYYMMDD`（不給則用今天）
  - calculator 實際執行：`calculate_daily.py -> calculate_trust_holding.py -> calculate_dealer_holding.py -> calculate_shareholding_concentration.py -> calculate_valuation.py`
  - 透傳 `FORCE_REPROCESS` / `FORCE_REIMPORT` 給 processor / audit / importer container（給 retry 在偵測到 stale 狀態時使用）

- `schedules/weekly_update.sh`
  - 流程：`scraper-weekly -> processor(convert_weekly) -> importer(shareholding)`
  - 自動偵測最新 TDCC 檔案日期後處理

- `schedules/monthly_update.sh`
  - 目標月份：自動抓「上個月」
  - 只在每月 1~15 日執行（公告窗口），其餘日期直接 skip
  - 流程：`scraper-monthly -> (day 15 only) generate_active_stocks -> processor(convert_monthly) -> importer(monthly_revenue, FORCE_REIMPORT=1)`

- `schedules/daily_retry.sh`
  - 檢查前一天的 daily_update 是否成功，失敗才重跑
  - 參數：可選 `YYYYMMDD`（不給則用昨天）
  - 判斷邏輯（三層完整性檢查，全綠才 skip）：
    1. **log**：`logs/daily_update_<target_date>_*.log` 是否含 `Daily Stock Data Update Completed`
    2. **raw**：8 個 daily category × `{sii,otc}` raw 檔是否存在且非 0 byte（含 `market_indices` otc-only）
    3. **DB**：8 個 daily 表 × `{sii,otc}` 該日是否都有資料（`market_indices` 因 symbol 是中文指數名暫時排除）
  - 修復路徑：
    - 非交易日（log 含 `No valid trading days`）→ skip
    - raw 缺 → 一般重跑（scraper 會補抓）
    - raw OK 但 DB 缺 → 設 `FORCE_REPROCESS=1` + `FORCE_REIMPORT=1` 讓 processor 重建 stale `processed/all.csv`、importer 覆寫 DB
    - log 沒成功 → 一般重跑全部
  - 由 launchd 在 02:00 及 04:00 各觸發一次

- `schedules/xbrl_run_pipeline.sh`
  - 流程：`scrape (fetch_xbrl) -> processor(convert_quarterly_xbrl) -> importer(import_xbrl) -> importer(import_quarterly_xbrl)`
  - 寫入 DB：`balance_sheet_xbrl` / `income_statement_xbrl` / `cash_flow_xbrl` / `xbrl_codebook` / `quarterly_reports_xbrl`
  - 參數：可選 `YYYYMMDD` 或 `YYYYQX`
  - 規則（不傳參數時，用今天日期判斷）：
    - `02/01~03/31`：抓「前一年 Q4」
    - `04/01~05/15`：抓「同年 Q1」
    - `07/01~08/15`：抓「同年 Q2」
    - `10/01~11/15`：抓「同年 Q3」
    - 其他日期：直接 skip
  - 透傳 `FORCE_REPROCESS` / `FORCE_REIMPORT` 給 processor / importer container

- `schedules/backfill_xbrl.sh`
  - 範圍補齊（多季）。**目前只跑 scrape 階段**（不含 processor/importer）；補完後仍須手動跑 processor + 兩個 importer，或對每季呼叫 `xbrl_run_pipeline.sh`。

- `schedules/_deprecated/quarterly_update.sh`
  - 已停用。原本流程是 `scraper-quarterly -> processor(convert_quarterly) -> importer(import_quarterly)`，餵的是 legacy 季報表。改用 `xbrl_run_pipeline.sh`。

## Logging

- 腳本都會將執行結果寫到 `logs/`，格式統一為 `<script>_<TARGET>_<EXEC_DATE>_<EXEC_TIME>.log`：
  - `daily_update_<TARGET_DATE>_<EXEC_DATE>_<EXEC_TIME>.log`（例：`daily_update_20260416_20260417_020000.log`）
  - `daily_retry_<TARGET_DATE>_<EXEC_DATE>_<EXEC_TIME>.log`
  - `weekly_update_<TARGET_DATE>_<EXEC_TS>.log`
  - `monthly_update_<YYYYMM>_<EXEC_TS>.log`（例：`monthly_update_202603_20260410_224500.log`）
  - `xbrl_pipeline_<YYYYQX>_<EXEC_TS>.log` / `xbrl_pipeline_skip_<EXEC_TS>.log`（視窗外時）

## launchd Only (macOS)

目前專案採用 `launchd`，不使用 `cron`。

### Plist 檔案位置

`schedules/` 目錄內的 `.plist` 是 **git 備份**，實際 launchd 讀取的是安裝到 `~/Library/LaunchAgents/` 的版本。兩者是獨立的檔案，不會自動同步。

| 備份（repo） | 安裝位置 |
|---|---|
| `schedules/com.poyilee.stock-daily-update.plist` | `~/Library/LaunchAgents/com.poyilee.stock-daily-update.plist` |
| `schedules/com.poyilee.stock-daily-retry-1.plist` | `~/Library/LaunchAgents/com.poyilee.stock-daily-retry-1.plist` |
| `schedules/com.poyilee.stock-daily-retry-2.plist` | `~/Library/LaunchAgents/com.poyilee.stock-daily-retry-2.plist` |
| `schedules/com.poyilee.stock-weekly-update.plist` | `~/Library/LaunchAgents/com.poyilee.stock-weekly-update.plist` |
| `schedules/com.poyilee.stock-monthly-update.plist` | `~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist` |
| `schedules/com.poyilee.stock-xbrl-run-pipeline.plist` | `~/Library/LaunchAgents/com.poyilee.stock-xbrl-run-pipeline.plist` |

### 初次安裝 / 重裝後還原

```bash
# 將 repo 內的 plist 複製到 LaunchAgents
cp schedules/com.poyilee.stock-daily-update.plist ~/Library/LaunchAgents/
cp schedules/com.poyilee.stock-weekly-update.plist ~/Library/LaunchAgents/
cp schedules/com.poyilee.stock-monthly-update.plist ~/Library/LaunchAgents/
cp schedules/com.poyilee.stock-xbrl-run-pipeline.plist ~/Library/LaunchAgents/

# 載入全部
for label in daily-update weekly-update monthly-update xbrl-run-pipeline; do
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.poyilee.stock-${label}.plist
done
```

### 修改 plist 後同步

```bash
# 1. 修改 schedules/ 內的 plist
# 2. 複製到 LaunchAgents
cp schedules/com.poyilee.stock-daily-update.plist ~/Library/LaunchAgents/

# 3. 重新載入
launchctl bootout gui/$(id -u)/com.poyilee.stock-daily-update
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.poyilee.stock-daily-update.plist
```

### Current LaunchAgents

| Label | Script | 時間 |
|---|---|---|
| `com.poyilee.stock-daily-update` | `schedules/daily_update.sh` | 每天 23:30 |
| `com.poyilee.stock-daily-retry-1` | `schedules/daily_retry.sh` | 每天 02:00 |
| `com.poyilee.stock-daily-retry-2` | `schedules/daily_retry.sh` | 每天 04:00 |
| `com.poyilee.stock-weekly-update` | `schedules/weekly_update.sh` | 每週日 10:20 |
| `com.poyilee.stock-monthly-update` | `schedules/monthly_update.sh` | 每天 22:45 |
| `com.poyilee.stock-xbrl-run-pipeline` | `schedules/xbrl_run_pipeline.sh` | 每天 23:50 |

### macOS 26.4 注意事項

macOS 26.4 (Tahoe) 起，launchd 無法將 `StandardOutPath`/`StandardErrorPath` 寫入 `~/Documents/` 路徑，會導致任務 exit 78 (EX_CONFIG) 且完全不執行。

所有 plist 的 stdout/stderr 已改為 `/tmp/`：
- `/tmp/launchd_daily_stdout.log` / `stderr`
- `/tmp/launchd_daily_retry1_stdout.log` / `stderr`
- `/tmp/launchd_daily_retry2_stdout.log` / `stderr`
- `/tmp/launchd_weekly_stdout.log` / `stderr`
- `/tmp/launchd_monthly_stdout.log` / `stderr`
- `/tmp/launchd_xbrl_run_pipeline_stdout.log` / `stderr`

真正的執行 log 仍由各 script 自己寫入 `logs/` 目錄（`logs/*_update_*.log`）。

## Common Commands

```bash
# 手動執行 daily（指定日期）
./schedules/daily_update.sh 20260214

# 手動執行 weekly
./schedules/weekly_update.sh

# 手動執行 monthly
./schedules/monthly_update.sh

# 手動執行 XBRL 全鏈路（以今天判斷）
./schedules/xbrl_run_pipeline.sh

# 手動執行 XBRL 全鏈路（指定日期判斷）
./schedules/xbrl_run_pipeline.sh 20260304

# 手動執行 XBRL 全鏈路（直接指定季度）
./schedules/xbrl_run_pipeline.sh 2025Q4
```

```bash
# 查看 launchd 任務狀態
launchctl print gui/$(id -u)/com.poyilee.stock-daily-update

# 重新載入某個 launch agent
launchctl bootout gui/$(id -u)/com.poyilee.stock-daily-update
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.poyilee.stock-daily-update.plist

# 手動立即觸發
launchctl kickstart -p gui/$(id -u)/com.poyilee.stock-daily-update
```

## Notes

- 執行腳本前請確認 Docker Desktop 已啟動。
- 若有改 Dockerfile/程式碼，請先重建相關 service image。
- 月腳本僅在每月 15 號更新專案根目錄的 `active_stocks.txt`。
- Daily/Weekly/Monthly 寫入對應 `logs/*_update_*.log`；XBRL 寫入 `logs/xbrl_pipeline_*.log`。
- plist 修改後務必同步 `schedules/` 備份並 commit。
