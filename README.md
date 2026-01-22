# 台股分析與預測專案 (Stock Analysis Project)

本專案是一個全方位的股票分析系統，涵蓋從數據抓取、指標運算、資料庫儲存到前端視覺化儀表板的完整 ETL 與 API 流程。

## 核心功能
- **自動化爬蟲**: 抓取上市 (SII) 與上櫃 (OTC) 的每日行情、三大法人、融資融券等原始資料。
- **強健 ETL 流程**: 清洗原始 CSV 雜訊、自動對齊標頭、處理編碼問題並標準化。
- **預先指標運算**: 自動計算價格均線 (MA5~240) 以及成交量均線 (VMA5~240)。
- **高效 API 服務**: 透過 FastAPI 提供高效能的數據查詢接口，支援排序與過濾。
- **視覺化儀表板**: 使用 Next.js + Tailwind 打造，支援日期選擇、多指標切換 (成交量、MA、VMA) 與排行榜呈現。

## 📊 策略回測實驗室 (Backtest Lab)

系統內建強大的回測引擎，專門驗證「量能爆發」策略的有效性。

### 交易策略：量能爆發 (Volume Breakout)
*   **買進訊號**: 當日成交量 > **5 倍** 的 10日成交量均線 (VMA10)。
*   **進場點**: 訊號出現後的**下一個交易日開盤價 (Open)**。
*   **出場點**: 持有 N 個交易日後以**收盤價 (Close)** 賣出 (預設 3 天)。

### 資金管理與參數
*   **策略模式 (Position Sizing)**:
    *   `Fixed Shares`: 固定買入張數 (例如每次 1 張)。
    *   `Fixed Amount`: 固定投入金額 (例如每次 10 萬，自動計算股數)。
*   **重複加碼 (Pyramiding)**:
    *   `Enabled`: 若持倉期間再次出現訊號，則繼續買入 (獲利最大化)。
    *   `Disabled`: 若已有持倉，忽略新訊號直到賣出 (風險控制)。

### 實測績效參考 (2025/05)
*測試條件：固定金額 10 萬、允許加碼*

| 持有天數 | 總獲利 (NT$) | ROI | 勝率 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| **3 天** | $330,639 | 0.80% | 43.45% | 獲利穩定 |
| **5 天** | $424,215 | 1.06% | 42.75% | 獲利提升 |
| **7 天** | **$689,786** | **1.73%** | **49.50%** | **最佳甜蜜點** |

*(註：以上數據僅供參考，不代表未來績效)*

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
```bash
START_DATE=20250102 END_DATE=20260119 docker-compose run --rm scraper
```

### 2. 清洗與標準化 (Processor)
支援指定日期過濾，只處理當天資料：
```bash
START_DATE=20260121 END_DATE=20260121 docker-compose run --rm processor
```

### 3. 匯入資料庫 (Importer)
支援指定日期過濾，只匯入當天資料 (推薦用於每日更新)：
```bash
START_DATE=20260121 END_DATE=20260121 docker-compose run --rm importer
```

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

## 目錄結構
- `scripts/`: 自動化維護腳本
- `scraper/`: 資料抓取模組 (Extract)
- `processor/`: 資料清洗模組 (Transform)
- `importer/`: 資料載入模組 (Load)
- `calculator/`: 指標運算模組 (Analysis)
- `backend/`: FastAPI 後端服務
- `frontend/`: Next.js 前端視覺化
- `data/`: 資料湖儲存中心 (Raw, Processed, Postgres)
