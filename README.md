# 台股分析與預測專案 (Stock Analysis Project)

本專案是一個全方位的股票分析系統，涵蓋從數據抓取、指標運算、資料庫儲存到前端視覺化儀表板的完整 ETL 與 API 流程。

## 核心功能
- **自動化爬蟲**: 抓取上市 (SII) 與上櫃 (OTC) 的每日行情、三大法人、融資融券、月營收及集保股權分散表。
- **強健 ETL 流程**: 清洗原始 CSV 雜訊、自動對齊標頭、處理編碼問題並標準化。
- **大盤指數整合**: 自動從每日行情檔中提取加權指數與櫃買指數數據，作為回測基準。
- **預先指標運算**: 自動計算價格均線 (MA5~240) 以及成交量均線 (VMA5~240)。
- **高效 API 服務**: 透過 FastAPI 提供高效能的數據查詢接口，支援排序與過濾。
- **視覺化儀表板**: 使用 Next.js + Tailwind 打造，支援日期選擇、多指標切換與排行榜呈現。

## 🚀 每日自動更新 (Daily Automation)

專案內建一個高度自動化的 Shell 腳本，可一次完成 `Scraper` -> `Processor` -> `Importer` -> `Calculator` 的所有流程。

### 使用方式
1. **更新今天 (預設)**:
   ```bash
   ./scripts/daily_update.sh
   ```

2. **更新特定日期**:
   ```bash
   ./scripts/daily_update.sh 20260121
   ```

## 🛠️ 模組介紹

### 1. Scraper (資料抓取)
位於 `scraper/`，負責從外部來源 (TWSE, TPEx, TDCC, MOPS) 取得原始資料。
- **每日行情**: 股價、成交量、法人買賣。
- **月營收**: 上市櫃公司每月營收。
- **集保股權**: 支援每週 Open Data 快照與歷史資料單檔回補 (使用 `fetch_tdcc_history.py`)。

### 2. Processor (資料處理)
位於 `processor/`，負責將原始 HTML/CSV 轉換為標準化格式。
- **個股處理**: 清洗數據、轉換型別。
- **大盤指數**: 自動從 `daily_quotes` 中分離出市場指數 (`market_indices`)。
- **月營收**: 格式轉換 (`convert_monthly_revenue.py`)。
- **集保股權分散表**: 合併個股 CSV (`convert_shareholding.py`)。

### 3. Importer (資料匯入)
位於 `importer/`，負責將處理後的 CSV 寫入 PostgreSQL 資料庫。
- 自動過濾 ETF (非個股)。
- 支援增量匯入。

### 4. Calculator (指標運算)
位於 `calculator/`，負責計算技術指標 (MA, VMA, RSI, MACD 等) 並寫回資料庫。

### 5. Backend (API 服務)
位於 `backend/`，基於 FastAPI 的高效能後端。
- 提供 RESTful API。
- 整合 PostgreSQL 查詢。

### 6. Frontend (前端介面)
位於 `frontend/`，基於 Next.js 的現代化儀表板。
- 互動式圖表。
- 數據篩選與排行。

### 7. Strategy & Backtester (策略與回測)
位於 `strategy/` 與 `backtester/`。
- **Strategy**: 定義核心交易邏輯 (如量能爆發)。
- **Backtester**: 歷史回測引擎，產生績效報告。

## 快速上手 (手動 Docker Compose)

```bash
# 1. 抓取每日行情 (交易日執行)
START_DATE=20250402 END_DATE=20250402 docker compose run --rm scraper-daily

# 2. 抓取月營收 (每月 10 日後執行)
REVENUE_YEAR=2025 REVENUE_MONTH=3 docker compose run --rm scraper-monthly

# 3. 抓取集保股權分散表 (每週五執行)
TDCC_DATE=20250321 docker compose run --rm scraper-weekly

# 4. 處理與匯入 (會自動處理個股與大盤指數)
docker compose run --rm processor
docker compose run --rm processor python convert_monthly_revenue.py
docker compose run --rm processor python convert_shareholding.py
docker compose run --rm importer

# 5. 啟動服務
docker compose up -d backend frontend pgadmin
```

## 目錄結構
```
root/
├── scripts/            # 自動化腳本
├── scraper/            # 爬蟲 (Extract)
├── processor/          # 資料清洗 (Transform)
├── importer/           # 資料匯入 (Load)
├── calculator/         # 指標運算
├── backend/            # API 伺服器
├── frontend/           # 網頁介面
├── strategy/           # 交易策略核心
├── backtester/         # 回測系統
├── common/             # 共用常數與工具
└── data/               # 資料存放區 (Raw/Processed)
```
