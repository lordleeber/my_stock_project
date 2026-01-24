# Stock Data Processor (資料清洗與轉換模組)

本模組負責將 Scraper 抓取的原始 CSV 資料 (`data/raw`) 進行清洗、型別轉換與欄位標準化，最終轉換為高效的 **CSV** 格式 (`data/processed`)（註：可設定為 Parquet，目前配置為 CSV 以便人工驗證）。

## 核心功能
- **強健的 CSV 讀取**: 自動處理證交所複雜的多表格結構（如每日行情），精準定位標頭行，忽略 BOM 與雜訊。
- **增量處理**: 
    - 支援 `START_DATE` 與 `END_DATE` 指定處理範圍。
    - **自動跳過**: 若目標檔案已存在，自動跳過不重複處理，節省時間。
- **格式轉換**: Raw CSV -> Cleaned CSV / Parquet。
- **型別強制**: 字串轉數值 (Float/Int)、民國年轉西元年 (Date)。
- **Schema 對齊**: 確保不同市場 (SII/OTC) 的資料擁有完全一致的欄位結構與順序。
- **資料驗證**: 內建**嚴格驗證機制**，確保轉換前後筆數完全一致（零誤差），數值誤差小於 1e-6。
- **月營收處理**: 專用的 `convert_revenue.py` 處理 MOPS 格式不固定的月營收報表，自動正規化欄位名稱與清洗數值。

## 環境變數 (Environment Variables)
| 變數名稱 | 說明 | 預設值 | 範例 |
| :--- | :--- | :--- | :--- |
| `START_DATE` | 起始日期 (YYYYMMDD) | 無 (處理所有日期) | `20230301` |
| `END_DATE` | 結束日期 (YYYYMMDD) | 無 (處理所有日期) | `20230301` |

## 模組說明
- `convert.py`: 每日行情 ETL 核心邏輯，負責遍歷 Raw 資料並執行轉換。
- `convert_revenue.py`: **[新增]** 月營收 ETL 邏輯，處理 `data/raw/revenue` 下的資料。
- `validator.py`: 資料驗證器，比對 Raw 與 Processed 數據的完整性。
- `utils.py`: 共用的資料讀取與清洗輔助函式，包含標頭定位邏輯。
- `schemas.py`: 定義欄位映射、數值型別與標準 Schema 結構。

## 如何使用 (Docker)

### 1. 編譯映像檔
```bash
docker build -t stock-processor ./processor
```

### 2. 執行轉換任務 (ETL)
將主機的 `data` 目錄掛載進容器：

**處理每日行情:**
```bash
docker run --rm -v $(pwd)/data:/app/data -e START_DATE=20230301 -e END_DATE=20230301 stock-processor
```

**處理月營收 (需指定執行腳本):**
```bash
docker run --rm -v $(pwd)/data:/app/data -e START_DATE=20250101 stock-processor python convert_revenue.py
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
│   │   ├── sii.csv
│   │   └── otc.csv
│   └── ...
├── revenue/             # 月營收資料
│   ├── 2025-01/
│   │   └── revenue_202501.csv
│   └── ...
├── institutional_investors/
└── ...
```
每個檔案內部皆包含 `date` 與 `market` 欄位，方便全市場數據合併查詢。
