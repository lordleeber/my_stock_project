# Stock Data Processor (資料清洗與轉換模組)

本模組負責將 Scraper 抓取的原始 CSV 資料 (`data/raw`) 進行清洗、型別轉換與欄位標準化，最終轉換為高效的 **Parquet** 格式 (`data/processed`)。

## 核心功能
- **格式轉換**: CSV -> Parquet (讀寫速度提升 10-50 倍)。
- **型別強制**: 字串轉數值 (Float/Int)、民國年轉西元年 (Date)。
- **欄位標準化**: 中文欄位映射為英文 (如 `收盤價` -> `close`)。
- **資料分區**: 依日期與市場分區儲存，優化查詢效能。
- **技術棧**: 使用 **Polars** (Rust-based DataFrame) 進行極速處理。

## 欄位映射 (Schema)
詳細的欄位中英文對照請參考 `schemas.py` 或專案根目錄的 `README.md`。

## 如何使用 (Docker)

### 1. 編譯映像檔
在專案根目錄執行：
```bash
docker build -t stock-processor ./processor
```

### 2. 執行轉換任務
將主機的 `data` 目錄掛載進容器，程式會自動掃描 `raw` 目錄下的所有 CSV 並進行轉換。

```bash
docker run --rm -v $(pwd)/data:/app/data stock-processor
```

### 3. 輸出結構
轉換後的資料將存放於 `data/processed/`：
```
data/processed/
├── daily_quotes/
│   ├── market=sii/
│   │   └── date=20230301/data.parquet
│   └── market=otc/
│       └── ...
├── institutional_investors/
└── ...
```
