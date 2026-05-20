# Schedules (macOS launchd)

> ⚠️ **Legacy**：Ubuntu 已取代 Mac 成為生產機，這個目錄保留只為了過渡期。Ubuntu 端排程走 `schedules_ubuntu/` 的 systemd timer。如果確定不再回頭用 Mac，可以整個 `schedules_macos/` 一併刪除。

這個目錄只負責「**Mac 上什麼時間呼叫哪支 .sh**」。實際做事的 shell 邏輯仍在 `schedules/*.sh`（cross-platform）。

## 為何要從 `schedules/` 拆出來？

舊版本所有東西都堆在 `schedules/`：launchd plist、systemd 也曾考慮過、cross-platform shell。隨著 Ubuntu 加入，OS-specific 內容拆分如下：

- `schedules_macos/` — launchd plist（這個目錄，archive）
- `schedules_ubuntu/` — systemd timer/service
- `schedules/` — 兩邊都呼叫的 shell script

兩種排程系統概念類似（時間表 → 觸發 ExecStart）但 unit 檔語法完全不同，所以無法共用同一份 unit。shell script 就沒這個問題了。

## Plist 檔案位置

`schedules_macos/` 內的 `.plist` 是 **git 備份**，實際 launchd 讀取的是安裝到 `~/Library/LaunchAgents/` 的版本。兩者是獨立的檔案，不會自動同步。

| 備份（repo） | 安裝位置 |
|---|---|
| `schedules_macos/com.poyilee.stock-daily-update.plist` | `~/Library/LaunchAgents/com.poyilee.stock-daily-update.plist` |
| `schedules_macos/com.poyilee.stock-daily-retry-1.plist` | `~/Library/LaunchAgents/com.poyilee.stock-daily-retry-1.plist` |
| `schedules_macos/com.poyilee.stock-daily-retry-2.plist` | `~/Library/LaunchAgents/com.poyilee.stock-daily-retry-2.plist` |
| `schedules_macos/com.poyilee.stock-weekly-update.plist` | `~/Library/LaunchAgents/com.poyilee.stock-weekly-update.plist` |
| `schedules_macos/com.poyilee.stock-monthly-update.plist` | `~/Library/LaunchAgents/com.poyilee.stock-monthly-update.plist` |
| `schedules_macos/com.poyilee.stock-xbrl-scrape-daily.plist` | `~/Library/LaunchAgents/com.poyilee.stock-xbrl-scrape-daily.plist` |

## 初次安裝 / 重裝後還原

```bash
# 將 repo 內的 plist 複製到 LaunchAgents
cp schedules_macos/com.poyilee.stock-daily-update.plist ~/Library/LaunchAgents/
cp schedules_macos/com.poyilee.stock-weekly-update.plist ~/Library/LaunchAgents/
cp schedules_macos/com.poyilee.stock-monthly-update.plist ~/Library/LaunchAgents/
cp schedules_macos/com.poyilee.stock-xbrl-scrape-daily.plist ~/Library/LaunchAgents/

# 載入全部
for label in daily-update weekly-update monthly-update xbrl-scrape-daily; do
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.poyilee.stock-${label}.plist
done
```

## 修改 plist 後同步

```bash
# 1. 修改 schedules_macos/ 內的 plist
# 2. 複製到 LaunchAgents
cp schedules_macos/com.poyilee.stock-daily-update.plist ~/Library/LaunchAgents/

# 3. 重新載入
launchctl bootout gui/$(id -u)/com.poyilee.stock-daily-update
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.poyilee.stock-daily-update.plist
```

## Current LaunchAgents

| Label | Script (cross-platform) | 時間 |
|---|---|---|
| `com.poyilee.stock-daily-update` | `schedules/daily_update.sh` | 每天 23:30 |
| `com.poyilee.stock-daily-retry-1` | `schedules/daily_retry.sh` | 每天 02:00 |
| `com.poyilee.stock-daily-retry-2` | `schedules/daily_retry.sh` | 每天 04:00 |
| `com.poyilee.stock-weekly-update` | `schedules/weekly_update.sh` | 每週日 10:20 |
| `com.poyilee.stock-monthly-update` | `schedules/monthly_update.sh` | 每天 22:45 |
| `com.poyilee.stock-xbrl-scrape-daily` | `schedules/xbrl_scrape_daily.sh` | 每天 23:50 |

## macOS 26.4 注意事項

macOS 26.4 (Tahoe) 起，launchd 無法將 `StandardOutPath`/`StandardErrorPath` 寫入 `~/Documents/` 路徑，會導致任務 exit 78 (EX_CONFIG) 且完全不執行。

所有 plist 的 stdout/stderr 已改為 `/tmp/`：
- `/tmp/launchd_daily_stdout.log` / `stderr`
- `/tmp/launchd_daily_retry1_stdout.log` / `stderr`
- `/tmp/launchd_daily_retry2_stdout.log` / `stderr`
- `/tmp/launchd_weekly_stdout.log` / `stderr`
- `/tmp/launchd_monthly_stdout.log` / `stderr`
- `/tmp/launchd_xbrl_scrape_daily_stdout.log` / `stderr`

真正的執行 log 仍由各 script 自己寫入 `logs/` 目錄（`logs/*_update_*.log`），由 `schedules/*.sh` 控制，跟平台無關。

## launchctl Operations

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

- 每支 .sh 的實際邏輯說明見 [`../schedules/CLAUDE.md`](../schedules/CLAUDE.md)。
- plist 修改後務必同步 `schedules_macos/` 備份並 commit。
