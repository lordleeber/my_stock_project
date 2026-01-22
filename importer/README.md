# Stock Data Importer (資料載入模組)

本模組負責將 `processor` 處理好的標準化 CSV 檔案匯入到 PostgreSQL 資料庫中。

## 核心功能
- **自動化匯入**: 掃描 `data/processed` 目錄下的所有類別與日期。
- **資料完整性**: 採用 "Delete-before-Insert" 策略，確保同一日期與市場的資料不會重複。
- **增量匯入支援**: 透過環境變數過濾日期，避免重複掃描舊資料，大幅提升每日更新效率。
- **資料庫等待機制**: 內建連線重試邏輯，確保資料庫啟動完成後才開始作業。

## 環境變數
- `DB_HOST`: 資料庫主機位址 (預設: `db`)
- `DB_USER`: 資料庫使用者 (預設: `user`)
- `DB_PASSWORD`: 資料庫密碼 (預設: `password`)
- `DB_NAME`: 資料庫名稱 (預設: `stock_db`)
- `START_DATE`: (選填) 起始日期 YYYYMMDD，僅處理此日期之後的資料。
- `END_DATE`: (選填) 結束日期 YYYYMMDD。

## 如何使用

### 1. 全量匯入 (掃描所有檔案)
```bash
docker-compose run --rm importer
```

### 2. 增量匯入 (推薦用於每日自動更新)
僅匯入指定日期的資料：
```bash
START_DATE=20260121 END_DATE=20260121 docker-compose run --rm importer
```

## 注意事項
- 匯入前請確保 `processor` 已經產生了對應日期的 Processed CSV。
- 為了效能考量，大批量資料會以 chunk 方式寫入。
