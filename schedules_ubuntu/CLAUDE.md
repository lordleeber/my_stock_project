# Schedules (Ubuntu) Guide

這份文件描述 `schedules_ubuntu/` 目錄裡的 **systemd --user** 排程單元，用於 Ubuntu 24.04（或其他 systemd-based Linux）。

實際的執行邏輯（scraper / processor / importer / calculator / XBRL）完全沿用 `schedules/` 目錄下的同名 `.sh`，這裡只負責「**什麼時間呼叫哪支 .sh**」。

## 為何不直接重用 `schedules_macos/` 的 plist？

`schedules_macos/*.plist` 是 macOS launchd 專用格式；Linux 用的是 systemd unit 檔。兩種排程系統概念類似但語法不同，所以 plist 必須轉成 `.service` + `.timer`。

## 目錄內容

| Unit | 觸發時間 | 呼叫的 script |
|---|---|---|
| `stock-daily-update.timer` | 每天 23:30 | `schedules/daily_update.sh` |
| `stock-daily-retry.timer` | 每天 02:00 與 04:00 | `schedules/daily_retry.sh` |
| `stock-weekly-update.timer` | 週日 10:20 | `schedules/weekly_update.sh` |
| `stock-monthly-update.timer` | 每天 22:45（script 內判斷 1~15 才實際跑） | `schedules/monthly_update.sh` |
| `stock-xbrl-scrape-daily.timer` | 每天 23:50（script 內判斷公告期才實際跑） | `schedules/xbrl_scrape_daily.sh` |

> **差異說明**：macOS 因 launchd `StartCalendarInterval` 不支援多時間點，所以拆成 `schedules_macos/com.poyilee.stock-daily-retry-1.plist` (02:00) 與 `-2.plist` (04:00) 兩個 plist。systemd 的 `OnCalendar=` 可以多行，所以 `stock-daily-retry.timer` 一支單元同時涵蓋兩個時間。

## 前置需求

1. **Docker**：安裝 Docker Engine + Compose plugin，並把使用者加入 `docker` 群組（避免 sudo）：
   ```bash
   sudo usermod -aG docker $USER
   newgrp docker   # 或登出再登入
   ```
2. **專案路徑**：unit 預設 `WorkingDirectory=%h/GitHubLL/my_stock_project`。若放在別處，把 `schedules_ubuntu/*.service` 裡的兩個路徑（`WorkingDirectory` 與 `ExecStart`）一起改掉。
3. **`logs/` 與 venv**：跟 macOS 相同，由各 `.sh` 自己處理。

## 安裝

```bash
# 1. 建立 user systemd 目錄並複製 unit
mkdir -p ~/.config/systemd/user
cp schedules_ubuntu/*.service schedules_ubuntu/*.timer ~/.config/systemd/user/

# 2. 讓 systemd reload + enable 所有 timer
systemctl --user daemon-reload
for t in stock-daily-update stock-daily-retry stock-weekly-update stock-monthly-update stock-xbrl-scrape-daily; do
  systemctl --user enable --now ${t}.timer
done

# 3. (重要) 讓 user units 在沒登入時也能跑
sudo loginctl enable-linger "$USER"
```

> 不開 linger 的話，登出後 user systemd 會結束，timer 不會觸發。

## 修改後同步

```bash
# 1. 修改 schedules_ubuntu/ 內檔案
# 2. 複製到 ~/.config/systemd/user/
cp schedules_ubuntu/stock-daily-update.timer ~/.config/systemd/user/

# 3. reload + restart
systemctl --user daemon-reload
systemctl --user restart stock-daily-update.timer
```

## 常用指令

```bash
# 列出所有已啟用的 timer
systemctl --user list-timers

# 看單一 timer / service 狀態
systemctl --user status stock-daily-update.timer
systemctl --user status stock-daily-update.service

# 手動立即觸發（不等到排程時間）
systemctl --user start stock-daily-update.service

# 看 service 的 stdout/stderr（即 docker compose 的輸出）
journalctl --user -u stock-daily-update.service -n 200 --no-pager
journalctl --user -u stock-daily-update.service -f         # follow

# 暫停某個 timer
systemctl --user disable --now stock-daily-update.timer
```

## Logging

- **systemd journal**：每次 service 執行的 stdout/stderr 都寫到 journal，用 `journalctl --user -u <unit>` 查。
- **script 內部 log**：`schedules/*.sh` 本身會在專案 `logs/` 裡寫 `daily_update_<date>_<ts>.log` 等檔案，由 cross-platform shell 邏輯控制，與 OS 無關。

不需要 macOS 那種 `/tmp/launchd_*_stdout.log` workaround（那是 macOS 26.4 launchd 不能寫 `~/Documents/` 的特殊問題）。

## 與 macOS schedules_macos/ 的差異速查

| 面向 | macOS (`schedules_macos/`) | Ubuntu (`schedules_ubuntu/`) |
|---|---|---|
| 排程引擎 | launchd | systemd --user |
| Unit 格式 | `.plist` (XML) | `.service` + `.timer` |
| 安裝目錄 | `~/Library/LaunchAgents/` | `~/.config/systemd/user/` |
| 載入 | `launchctl bootstrap gui/$(id -u) ...` | `systemctl --user enable --now ...` |
| 手動觸發 | `launchctl kickstart -p gui/$(id -u)/<label>` | `systemctl --user start <unit>` |
| stdout/stderr | 寫到 `/tmp/launchd_*.log` | `journalctl --user -u <unit>` |
| Retry 兩時間點 | 拆成 2 個 plist | 1 個 timer + 2 行 `OnCalendar=` |
| 登出後仍跑 | launchd `gui/<uid>` agent 保留 | 需 `loginctl enable-linger $USER` |

## Notes

- 執行前確認 Docker daemon 在跑：`systemctl status docker`（system service，不是 user）。
- 若改了 `schedules/*.sh`，systemd 端通常不用動；只有改觸發時間或新增任務時才需要改這裡的 unit。
- 修改 unit 後務必跑 `systemctl --user daemon-reload`，否則新內容不會生效。
