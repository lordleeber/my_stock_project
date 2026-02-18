# Schedules Guide

這份文件描述 `schedules/` 目錄目前的自動化腳本與排程方式。

## Available Scripts

- `schedules/daily_update.sh`
  - 流程：`scraper-daily -> processor -> audit -> importer -> calculator`
  - 參數：可選 `YYYYMMDD`（不給則用今天）
  - calculator 實際執行：`calculate_daily.py -> calculate_trust_holding.py -> calculate_valuation.py`

- `schedules/weekly_update.sh`
  - 流程：`scraper-weekly -> processor(convert_weekly) -> importer(shareholding)`
  - 自動偵測最新 TDCC 檔案日期後處理

- `schedules/monthly_update.sh`
  - 目標月份：自動抓「上個月」
  - 只在每月 1~15 日執行（公告窗口），其餘日期直接 skip
  - 流程：`scraper-monthly -> (day 15 only) generate_active_stocks -> processor(convert_monthly) -> importer(monthly_revenue, FORCE_REIMPORT=1)`

- `schedules/quarterly_update.sh`
  - 流程：`scraper-quarterly -> processor(convert_quarterly) -> importer(quarterly categories)`
  - 參數：可選 `YYYYQX`（不給則用上一季）

## Logging

- 腳本都會將執行結果寫到 `logs/`：
  - `daily_update_*.log`
  - `weekly_update_*.log`
  - `monthly_update_*.log`
  - `quarterly_update_*.log`

## launchd Only (macOS)

目前專案採用 `launchd`，不使用 `cron`。

### Current LaunchAgents

- `com.poyilee.stock-daily-update`
- `com.poyilee.stock-weekly-update`
- `com.poyilee.stock-monthly-update`

### Daily Schedule (current)

`com.poyilee.stock-daily-update`：
- Script: `StockDailyUpdate.app`（內部呼叫 `schedules/daily_update.sh`）
- Time: 每天 `23:00`

### Monthly Schedule (current)

`com.poyilee.stock-monthly-update`：
- Script: `schedules/monthly_update.sh`
- Time: 每天 `22:45`（腳本內再判斷是否在 1~15 日）

### Weekly Schedule (current)

`com.poyilee.stock-weekly-update`：
- Script: `schedules/weekly_update.sh`
- Time: 每週六 `14:10`

## Common Commands

```bash
# 手動執行 daily（指定日期）
./schedules/daily_update.sh 20260214

# 手動執行 weekly
./schedules/weekly_update.sh

# 手動執行 monthly
./schedules/monthly_update.sh

# 手動執行 quarterly（指定季度）
./schedules/quarterly_update.sh 2025Q3
```

```bash
# 查看 launchd 任務狀態
launchctl print gui/$(id -u)/com.poyilee.stock-monthly-update

# 重新載入某個 launch agent
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist
```

## Notes

- 執行腳本前請確認 Docker Desktop 已啟動。
- 若有改 Dockerfile/程式碼，請先重建相關 service image。
- 月腳本僅在每月 15 號更新專案根目錄的 `active_stocks.txt`。
- Daily/Weekly/Monthly/Quarterly 都會寫入對應 `logs/*_update_*.log`。
