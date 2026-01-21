# 台股分析與預測專案 (Stock Analysis Project)

本專案是一個全方位的股票分析系統，涵蓋從數據抓取、指標運算、資料庫儲存到前端視覺化儀表板的完整 ETL 與 API 流程。

## 核心功能
- **自動化爬蟲**: 抓取上市 (SII) 與上櫃 (OTC) 的每日行情、三大法人、融資融券等原始資料。
- **強健 ETL 流程**: 清洗原始 CSV 雜訊、自動對齊標頭、處理編碼問題並標準化。
- **預先指標運算**: 自動計算 KD (9, 3, 3)、RSI (14)、價格均線 (MA5~240) 以及成交量均線 (VMA5~240)。
- **高效 API 服務**: 透過 FastAPI 提供高效能的數據查詢接口，支援排序與過濾。
- **視覺化儀表板**: 使用 Next.js + Tailwind 打造，支援日期選擇、多指標切換 (成交量、KD、RSI、MA、VMA) 與排行榜呈現。

## 快速上手 (Docker Compose)

### 1. 抓取原始資料 (Scraper)
```bash
START_DATE=20250102 END_DATE=20260119 docker-compose up --build scraper
```

### 2. 清洗與標準化 (Processor)
```bash
docker-compose up --build processor
```

### 3. 匯入資料庫 (Importer)
```bash
docker-compose up --build importer
```

### 4. 計算技術指標 (Calculator)
```bash
docker-compose up --build calculator
```

### 5. 啟動常駐服務 (Backend / Frontend / pgAdmin)
```bash
docker-compose up -d backend frontend pgadmin
```
- **前端頁面**: `http://localhost:3000`
- **API 文檔**: `http://localhost:8000/docs`
- **資料庫管理**: `http://localhost:5050`

## 目錄結構
- `scraper/`: 資料抓取模組 (Extract)
- `processor/`: 資料清洗模組 (Transform)
- `importer/`: 資料載入模組 (Load)
- `calculator/`: 指標運算模組 (Analysis)
- `backend/`: FastAPI 後端服務
- `frontend/`: Next.js 前端視覺化
- `data/`: 資料湖儲存中心 (Raw, Processed, Postgres)
