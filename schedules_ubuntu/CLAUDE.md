# Schedules (Ubuntu) Guide

這份文件描述 `schedules_ubuntu/` 目錄裡的 **systemd --user** 排程單元，用於 Ubuntu 24.04（或其他 systemd-based Linux）。

實際的執行邏輯（scraper / processor / importer / calculator / XBRL）完全沿用 `schedules/` 目錄下的同名 `.sh`，這裡只負責「**什麼時間呼叫哪支 .sh**」。

## 目錄內容

| Unit | 觸發時間 | 呼叫的 script |
|---|---|---|
| `stock-daily-update.timer` | 每天 23:30 | `schedules/daily_update.sh` |
| `stock-daily-retry.timer` | 每天 03:00 | `schedules/daily_retry.sh` |
| `stock-weekly-update.timer` | 週日 10:20 | `schedules/weekly_update.sh` |
| `stock-monthly-update.timer` | 每天 22:45（script 內判斷 1~15 才實際跑） | `schedules/monthly_update.sh` |
| `stock-xbrl-scrape-daily.timer` | 每天 23:50（script 內判斷公告期才實際跑） | `schedules/xbrl_scrape_daily.sh` |
| `stock-playbook-run.timer` | 每月 11 號與 16 號 04:00（script self-gate 到 canonical playbook 那天） | `schedules/playbook_run.sh` |

> 過往用 02:00 + 04:00 兩個觸發點；2026-05 簡化成單一 03:00，因為觀察上兩次 retry 結果幾乎總是一致（同時 skip 或同時 fail，沒看到「02:00 fail / 04:00 success」案例），多排一次只是重複跑 + 多一次通知噪音。

## 前置需求

1. **Docker**：安裝 Docker Engine + Compose plugin，並把使用者加入 `docker` 群組（避免 sudo）：
   ```bash
   sudo usermod -aG docker $USER
   newgrp docker   # 或登出再登入
   ```
2. **專案路徑**：unit 預設 `WorkingDirectory=%h/GitHubLL/my_stock_project`。若放在別處，把 `schedules_ubuntu/*.service` 裡的兩個路徑（`WorkingDirectory` 與 `ExecStart`）一起改掉。
3. **`logs/` 與 venv**：由各 `.sh` 自己處理，unit 不需額外設定。

## 安裝

```bash
# 1. 建立 user systemd 目錄並複製 unit
mkdir -p ~/.config/systemd/user
cp schedules_ubuntu/*.service schedules_ubuntu/*.timer ~/.config/systemd/user/

# 2. 讓 systemd reload + enable 所有 timer
systemctl --user daemon-reload
for t in stock-daily-update stock-daily-retry stock-weekly-update stock-monthly-update stock-xbrl-scrape-daily stock-playbook-run; do
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

## Failure Notification（ntfy.sh 手機推播）

大部分 timer-driven service 掛了 `OnFailure=stock-notify@%n.service`。任何 service 跑出 non-zero exit code，systemd 會自動觸發 `stock-notify@<failed-unit>.service`，由 `notify_failure.sh` 抓該 unit 最近 10 行 journal 後 POST 到 ntfy.sh 推到手機。

**例外：`stock-daily-update.service` 不掛通知**。23:30 scraper 對 TWSE/TPEx 抓資料常 transient fail，但 03:00 排程的 `stock-daily-retry.service` 通常會救回（見 `schedules/daily_retry.sh` 三層 log/raw/db 檢查）。把通知掛在 daily-update 會半夜被假警報吵醒；改掛 retry 端，只有 retry 也炸（= 問題真的卡住）才推播。其他 5 個 service（weekly / monthly / xbrl / daily-retry / playbook-run）沒有 retry 救援，照常立即通知。

### 元件

| 檔案 | 位置 | 角色 |
|---|---|---|
| `notify_failure.sh` | `schedules_ubuntu/`（in repo） | curl POST 腳本，吃 `$NTFY_TOPIC` env var |
| `stock-notify@.service` | `schedules_ubuntu/` + `~/.config/systemd/user/` | template service，`%i` = 失敗的 unit 名 |
| `stock-notify.env.example` | `schedules_ubuntu/`（in repo） | env 檔範本（**不含真實 topic**） |
| `stock-notify.env` | `~/.config/systemd/user/`（**不入 git**，權限 600） | 含真實 `NTFY_TOPIC` |
| `OnFailure=stock-notify@%n.service` | 5 個 timer service 的 `[Unit]` 區塊 | 觸發 hook |

### 安裝

```bash
# 1. 從範本建 env 檔，把 NTFY_TOPIC 改成 hard-to-guess 字串
cp schedules_ubuntu/stock-notify.env.example ~/.config/systemd/user/stock-notify.env
vim ~/.config/systemd/user/stock-notify.env   # 把 CHANGE-ME-TO-RANDOM 改成隨機字串
chmod 600 ~/.config/systemd/user/stock-notify.env

# 2. 部署 template service（連同其他 unit 一起 cp 過去）
cp schedules_ubuntu/stock-notify@.service ~/.config/systemd/user/

# 3. reload（service 改動後）
systemctl --user daemon-reload
```

### 訂閱推播（手機）

1. 裝 [ntfy.sh App](https://ntfy.sh/app)（iOS / Android）
2. 開 app → "+" → "Subscribe to topic" → 輸入 `stock-notify.env` 裡的 `NTFY_TOPIC`，server 留預設 `ntfy.sh`
3. 失敗推播會即時到通知中心

### 測試

```bash
# 1. 不依賴真的失敗：直接觸發 template service
systemctl --user start stock-notify@stock-daily-update.service
# → 會 POST 一則含 stock-daily-update.service journal 最後 10 行的推播

# 2. 完整 OnFailure 流程：手動失敗
systemctl --user start stock-fake-test.service  # 不存在的 unit → 觸發失敗
# 或讓現有 service exit 1，例如改 ExecStart 為 /bin/false 暫時測試
```

### 改 topic

```bash
vim ~/.config/systemd/user/stock-notify.env
# EnvironmentFile 每次啟動都讀，不需要 daemon-reload
```

### 注意事項

- **Public ntfy.sh 的 topic 名等同密碼** — 任何人猜到都能讀寫。挑 hard-to-guess（建議 ≥ 12 隨機字元）。需要隱私升級的話走 Telegram bot / self-host ntfy。
- **無網路時通知會 fail** — `notify_failure.sh` 本身不再有 `OnFailure=`，所以 fail 就只是吞掉，不會無限遞迴。
- **計算用 `journalctl --user -u <unit> -n 12`**，所以 unit 沒跑過的話會收到 "No entries" — 測試假 unit 名時是正常現象。
- **不通知「資料舊但沒 crash」這類 silent failure**。若要抓「process exit 0 但 DB 沒進資料」的情境，需另寫 freshness-check cron（未做）。

## 速查

| 面向 | 做法 |
|---|---|
| 排程引擎 | systemd --user |
| Unit 格式 | `.service` + `.timer` |
| 安裝目錄 | `~/.config/systemd/user/` |
| 載入 | `systemctl --user enable --now ...` |
| 手動觸發 | `systemctl --user start <unit>` |
| stdout/stderr | `journalctl --user -u <unit>` |
| Retry 兩時間點 | 1 個 timer + 2 行 `OnCalendar=` |
| 登出後仍跑 | 需 `loginctl enable-linger $USER` |

## Notes

- 執行前確認 Docker daemon 在跑：`systemctl status docker`（system service，不是 user）。
- 若改了 `schedules/*.sh`，systemd 端通常不用動；只有改觸發時間或新增任務時才需要改這裡的 unit。
- 修改 unit 後務必跑 `systemctl --user daemon-reload`，否則新內容不會生效。
