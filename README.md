# 台股分析與預測專案 (Stock Analysis Project)

本專案是一個全方位的股票分析系統，涵蓋從數據抓取、指標運算、資料庫儲存到前端視覺化儀表板的完整 ETL 與 API 流程。

## 核心功能
- **自動化爬蟲**: 抓取上市 (SII) 與上櫃 (OTC) 的每日行情、三大法人、融資融券等原始資料。
- **強健 ETL 流程**: 清洗原始 CSV 雜訊、自動對齊標頭、處理編碼問題並標準化。
- **預先指標運算**: 自動計算價格均線 (MA5~240) 以及成交量均線 (VMA5~240)。
- **高效 API 服務**: 透過 FastAPI 提供高效能的數據查詢接口，支援排序與過濾。
- **視覺化儀表板**: 使用 Next.js + Tailwind 打造，支援日期選擇、多指標切換 (成交量、MA、VMA) 與排行榜呈現。

## 📊 策略回測實驗室 (Backtest Lab)

系統內建回測引擎，專門驗證交易策略的有效性。

### 核心策略：量能爆發 (Volume Breakout)
此策略假設「成交量異常放大」代表有主力或法人進場，後續股價容易有波段行情。

*   **詳細交易規則與參數設定**：請參考 [backtester/README.md](./backtester/README.md)
*   **支援功能**:
    *   自定義訊號觸發條件 (如 VMA 倍數)。
    *   多種資金管理模式 (固定股數、固定金額)。
    *   進階濾網 (如紅 K 棒過濾) *(開發中)*。

---

## 🚀 每日自動更新 (Daily Automation)

專案內建一個高度自動化的 Shell 腳本，可一次完成 `Scraper` -> `Processor` -> `Importer` -> `Calculator` 的所有流程。

### 使用方式
1. **更新今天 (預設)**:
   ```bash
   ./scripts/daily_update.sh
   ```
   *這將會自動抓取今天的資料，並進行增量匯入與重算指標。*

2. **更新特定日期**:
   ```bash
   ./scripts/daily_update.sh 20260121
   ```

### 自動化特色
- **自動重新建置**: 腳本會先確保 Docker 容器是最新版本 (`docker-compose build`)。
- **增量處理**: Importer 會智慧識別日期，只處理該日期的資料，大幅節省時間。
- **錯誤中斷**: 若任何一個步驟失敗，腳本會立即停止並回報錯誤。

---

## 快速上手 (手動 Docker Compose)

如果您想手動執行個別服務，請參考以下指令：

### 1. 抓取原始資料 (Scraper)

#### 每日行情資料
```bash
START_DATE=20250102 END_DATE=20260119 docker-compose run --rm scraper
```

#### 月營收資料 (Monthly Revenue)
抓取上市櫃公司每月營收統計表：
```bash
# 抓取指定年月 (例如 2025年 3月)
docker-compose run --rm scraper python fetch_monthly_revenue.py --year 2025 --month 3

# 預設抓取「上個月」資料
docker-compose run --rm scraper python fetch_monthly_revenue.py
```

處理月營收數據：
```bash
START_DATE=20250301 END_DATE=20250331 docker-compose run --rm processor python convert_revenue.py
```

匯入月營收到資料庫（只匯入月營收，不重新處理其他數據）：
```bash
docker-compose run --rm -e IMPORT_CATEGORY=revenue -e START_DATE=20250301 -e END_DATE=20250331 importer
```

### 2. 清洗與標準化 (Processor)
支援指定日期過濾，只處理當天資料：
```bash
START_DATE=20260121 END_DATE=20260121 docker-compose run --rm processor
```

### 3. 匯入資料庫 (Importer)

**匯入所有類別的資料：**
```bash
START_DATE=20260121 END_DATE=20260121 docker-compose run --rm importer
```

**只匯入特定類別（推薦，避免重複處理）：**
```bash
# 只匯入每日報價
docker-compose run --rm -e IMPORT_CATEGORY=daily_quotes -e START_DATE=20260121 -e END_DATE=20260121 importer

# 只匯入月營收
docker-compose run --rm -e IMPORT_CATEGORY=revenue -e START_DATE=20250301 -e END_DATE=20250331 importer
```

> **注意**: Importer 會自動過濾 ETF（代號以 "00" 開頭），因為 ETF 沒有月營收、本益比等基本面數據。

### 4. 計算技術指標 (Calculator)
因為移動平均線需要歷史數據，Calculator 總是會進行全量運算：
```bash
docker-compose run --rm calculator
```

### 5. 啟動常駐服務 (Backend / Frontend / pgAdmin)
```bash
docker-compose up -d backend frontend pgadmin
```
- **前端頁面**: `http://localhost:3000`
- **API 文檔**: `http://localhost:8000/docs`
- **資料庫管理**: `http://localhost:5050`

## 資料庫結構
系統使用 PostgreSQL 儲存以下資料：
- `daily_quotes`: 每日報價（不含 ETF）
- `foreign_holding`: 外資持股
- `institutional_investors`: 法人買賣
- `margin_sbl`: 融券
- `margin_trading`: 融資
- `pe_ratio`: 本益比
- `monthly_revenue`: 月營收（2025 Q1 起）
- `technical_indicators`: 技術指標 (MA, VMA)

## 目錄結構
- `scripts/`: 自動化維護腳本
- `scraper/`: 資料抓取模組 (Extract) - 支援每日行情與月營收資料
- **`processor/` (Data Processor)**: **資料處理模組 (Transform & Load)**。負責清洗 CSV 資料（去除逗號、型別轉換、標頭重命名），並轉換為高效的 **CSV/Parquet** 格式。內建資料驗證器 (`validator.py`)。支援月營收資料處理 (`convert_revenue.py`)。
- **`importer/` (Data Importer)**: **資料載入模組**。將處理後的數據匯入 PostgreSQL，支援分類過濾（只匯入特定類型）與自動過濾 ETF。
- **`strategy/` (Core Strategy)**: **核心策略模組**。封裝交易邏輯 (如量能爆發、停損停利)，作為 Backend 與 Backtester 的共用核心 (Single Source of Truth)。
- **`backtester/` (Backtest Engine)**: **策略回測模組**。負責讀取歷史資料進行交易策略模擬，並產出績效報告。
- **`common/` (Shared Commons)**: **共用模組**。存放跨模組的常數設定（如中英文類別映射表 `CATEGORY_MAP`）。

# ... (跳到 各模組詳細說明)

### 5. 模型訓練 (Model Training)
*   **職責:** 對從資料庫中獲取的歷史數據進行深入分析... (略)

### 6. 核心策略模組 (Core Strategy)
*   **職責:** 專案的「策略大腦」，定義所有交易訊號產生邏輯、進出場規則與資金管理模型。
*   **設計:** 獨立於 UI 與執行環境的純 Python 模組，確保 Web API 與 CLI 回測工具的行為完全一致。
*   **目前策略:** 量能爆發 (Volume Breakout)、紅 K 濾網、停損停利機制。

### 7. 回測系統 (Backtesting)
*   **職責:** 根據歷史股票數據，嚴格測試和評估交易策略的效能... (略)

### 8. 非同步任務佇列 (Task Queue)
*   **職責:** 處理所有耗時且不需即時回應的背景任務... (略)
- `calculator/`: 指標運算模組 (Analysis)
- `backend/`: FastAPI 後端服務
- `frontend/`: Next.js 前端視覺化
- `data/`: 資料湖儲存中心
  - `raw/`: 原始資料 (每日行情、月營收等)
  - `processed/`: 處理後的標準化數據 (CSV/Parquet)
  - `postgres/`: PostgreSQL 資料庫持久化目錄