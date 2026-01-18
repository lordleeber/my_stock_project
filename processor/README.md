# Stock Data Processor (資料清洗與轉換模組)

本模組負責將 Scraper 抓取的原始 CSV 資料 (`data/raw`) 進行清洗、型別轉換與欄位標準化，最終轉換為高效的 **Parquet** 格式 (`data/processed`)。

## 核心功能
- **格式轉換**: CSV -> Parquet (讀寫速度提升 10-50 倍)。
- **型別強制**: 字串轉數值 (Float/Int)、民國年轉西元年 (Date)。
- **Schema 對齊**: 確保不同市場 (SII/OTC) 的資料擁有完全一致的欄位結構與順序。
- **資料分區**: 採用日期優先的 Hive 分區結構 (`category/date=YYYYMMDD/market.parquet`)。
- **資料驗證**: 內建驗證機制，確保轉換前後筆數與關鍵數值 (如 Close) 的一致性。

## 模組說明
- `convert.py`: ETL 核心邏輯，負責遍歷 Raw 資料並執行轉換。
- `validator.py`: 資料驗證器，比對 Raw 與 Processed 數據的完整性。
- `utils.py`: 共用的資料讀取與清洗輔助函式。
- `schemas.py`: 定義欄位映射、數值型別與標準 Schema 結構。

## 如何使用 (Docker)

### 1. 編譯映像檔
```bash
docker build -t stock-processor ./processor
```

### 2. 執行轉換任務 (ETL)
將主機的 `data` 目錄掛載進容器：
```bash
docker run --rm -v $(pwd)/data:/app/data stock-processor
```

### 3. 執行資料驗證 (Validation)
轉換完成後，建議執行驗證以確保資料品質：
```bash
docker run --rm -v $(pwd)/data:/app/data stock-processor python validator.py
```

## 輸出結構
轉換後的資料存放於 `data/processed/`，結構如下：
```
data/processed/
├── daily_quotes/
│   ├── date=20230301/
│   │   ├── sii.parquet
│   │   └── otc.parquet
│   └── ...
├── institutional_investors/
└── ...
```
每個 Parquet 檔案內部皆包含 `date` 與 `market` 欄位，方便全市場數據合併查詢。