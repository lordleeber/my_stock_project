# 每日自動更新設定指南

## 腳本說明

`daily_update.sh` 會自動執行完整的 ETL pipeline：
1. Scraper - 抓取今日資料
2. Processor - 處理每日資料
3. Processor (institutional_summary) - 處理三大法人資料
4. Importer - 匯入資料庫
5. Calculator - 計算技術指標

執行記錄會儲存在 `logs/` 目錄，並自動清理 30 天前的日誌。

---

## 方案 1: 使用 cron（Linux 推薦 / macOS 可用）

### Linux 設定步驟

1. 編輯 crontab：
```bash
crontab -e
```

2. 加入以下設定（每天晚上 8 點執行）：
```
0 20 * * * /Users/poyilee/Documents/GitHubLL/my_stock_project/scripts/daily_update.sh
```

3. 儲存並退出。驗證設定：
```bash
crontab -l
```

### macOS 設定步驟

1. 給予 cron 完整磁碟存取權限：
   - 系統設定 → 隱私權與安全性 → 完整磁碟取用權限
   - 加入 `/usr/sbin/cron`

2. 編輯 crontab：
```bash
crontab -e
```

3. 加入以下設定（每天晚上 8 點執行）：
```
0 20 * * * /Users/poyilee/Documents/GitHubLL/my_stock_project/scripts/daily_update.sh
```

4. 儲存並退出。驗證設定：
```bash
crontab -l
```

**注意**: macOS 上 cron 可能會有權限問題，如果遇到問題請使用方案 2。

---

## 方案 2: 使用 launchd（macOS 官方推薦）

### 設定步驟

1. 創建 plist 檔案：
```bash
nano ~/Library/LaunchAgents/com.stock.dailyupdate.plist
```

2. 貼上以下內容：
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.stock.dailyupdate</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/Users/poyilee/Documents/GitHubLL/my_stock_project/scripts/daily_update.sh</string>
    </array>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>20</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>/Users/poyilee/Documents/GitHubLL/my_stock_project/logs/launchd_stdout.log</string>
    
    <key>StandardErrorPath</key>
    <string>/Users/poyilee/Documents/GitHubLL/my_stock_project/logs/launchd_stderr.log</string>
    
    <key>WorkingDirectory</key>
    <string>/Users/poyilee/Documents/GitHubLL/my_stock_project</string>
    
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

3. 載入任務：
```bash
launchctl load ~/Library/LaunchAgents/com.stock.dailyupdate.plist
```

4. 驗證任務已載入：
```bash
launchctl list | grep stock
```

5. 測試立即執行（可選）：
```bash
launchctl start com.stock.dailyupdate
```

### 管理 launchd 任務

- **卸載任務**：
```bash
launchctl unload ~/Library/LaunchAgents/com.stock.dailyupdate.plist
```

- **查看狀態**：
```bash
launchctl list com.stock.dailyupdate
```

- **查看日誌**：
```bash
tail -f ~/Documents/GitHubLL/my_stock_project/logs/launchd_stdout.log
tail -f ~/Documents/GitHubLL/my_stock_project/logs/launchd_stderr.log
```

---

## 測試腳本

在設定排程前，建議先手動測試：

```bash
cd /Users/poyilee/Documents/GitHubLL/my_stock_project
./scripts/daily_update.sh
```

查看日誌：
```bash
tail -f logs/daily_update_*.log
```

---

## 注意事項

1. **Docker 需要啟動**：確保 Docker Desktop 正在運行
2. **資料庫需要啟動**：確保 PostgreSQL 容器正在運行
3. **網路連線**：確保有網路連線可以抓取資料
4. **磁碟空間**：定期檢查日誌和資料目錄的空間使用
5. **時區**：確認系統時區正確（台灣為 UTC+8）

---

## 進階配置

### 修改執行時間

**cron 格式**：`分 時 日 月 星期`
```
# 每天早上 9:30
30 9 * * *

# 每週一到週五晚上 8 點
0 20 * * 1-5

# 每月 1 號晚上 8 點
0 20 1 * *
```

**launchd 格式**：修改 plist 中的 `StartCalendarInterval`
```xml
<!-- 每週一到週五晚上 8 點 -->
<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>20</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <dict>
        <key>Weekday</key>
        <integer>2</integer>
        <key>Hour</key>
        <integer>20</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <!-- ... 繼續其他工作日 ... -->
</array>
```

---

## 疑難排解

### cron 沒有執行

1. 檢查 cron 服務是否運行：
```bash
# Linux
sudo systemctl status cron

# macOS
sudo launchctl list | grep cron
```

2. 檢查郵件（cron 會將錯誤發送到郵件）：
```bash
mail
```

3. 確認腳本路徑為絕對路徑

### launchd 沒有執行

1. 檢查 plist 語法：
```bash
plutil -lint ~/Library/LaunchAgents/com.stock.dailyupdate.plist
```

2. 查看系統日誌：
```bash
log show --predicate 'process == "launchd"' --info --last 1h
```

3. 重新載入：
```bash
launchctl unload ~/Library/LaunchAgents/com.stock.dailyupdate.plist
launchctl load ~/Library/LaunchAgents/com.stock.dailyupdate.plist
```
