# 台股分析與預測專案 (Stock Analysis Project)

本專案是一個全方位的股票分析系統，涵蓋從數據抓取、指標運算、資料庫儲存到前端視覺化儀表板的完整 ETL 與 API 流程。

## 核心功能
- **自動化爬蟲**: 抓取上市 (SII) 與上櫃 (OTC) 的每日行情、三大法人、融資融券、月營收及集保股權分散表。
- **強健 ETL 流程**: 清洗原始 CSV 雜訊、自動對齊標頭、處理編碼問題並標準化。
- **大盤指數整合**: 自動從每日行情檔中提取加權指數與櫃買指數數據，作為回測基準。
- **預先指標運算**: 自動計算價格均線 (MA5~240) 以及成交量均線 (VMA5~240)、KD、RSI、MACD、布林通道。
- **爆量掃描器** 🆕: 即時掃描異常放量股票，自動過濾長上影線與季線下個股，提供互動式 K 線圖分析。
- **高效 API 服務**: 透過 FastAPI 提供高效能的數據查詢接口，支援排序與過濾。
- **視覺化儀表板**: 使用 Next.js + Tailwind 打造，支援日期選擇、多指標切換、策略回測與爆量掃描。

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
- **三大法人買賣超彙總**: 標準化 SII/OTC 法人進出 (`convert_institutional_summary.py`)。

### 3. Importer (資料匯入)
位於 `importer/`，負責將處理後的 CSV 寫入 PostgreSQL 資料庫。
- 自動過濾 ETF (非個股)。
- 支援增量匯入。

### 4. Calculator (指標運算)
位於 `calculator/`，負責計算技術指標 (MA, VMA, RSI, MACD 等) 並寫回資料庫。

### 5. Scanner (爆量掃描器) 🆕
位於 `scanner/`，專注於異常放量股票的即時掃描。
- **智能篩選**: 自動計算成交量與過去 N 日均量比值。
- **型態過濾**: 排除長上影線 (拉高出貨) 型態與季線下個股。
- **技術指標**: 整合 MA、RSI、KD、MACD 等指標輔助判斷。
- **K線圖表**: 提供互動式專業 K 線圖，含均線與成交量。

### 6. Backend (API 服務)
位於 `backend/`，基於 FastAPI 的高效能後端。
- 提供 RESTful API (含掃描器、K線資料端點)。
- 整合 PostgreSQL 查詢。
- 回測引擎 API。

### 7. Frontend (前端介面)
位於 `frontend/`，基於 Next.js 的現代化儀表板。
- **策略回測**: 視覺化回測結果與交易明細。
- **爆量掃描器** 🆕: 日期選擇 + 參數調整 + 即時掃描 + K線圖表。
- **互動圖表**: 使用 lightweight-charts 提供專業金融圖表。

### 8. Strategy & Backtester (策略與回測)
位於 `strategy/` 與 `backtester/`。
- **Strategy**: 定義核心交易邏輯 (如量能爆發)。
- **Backtester**: 歷史回測引擎，產生績效報告。

### 9. Deep Learning (深度學習交易系統) 🆕
位於 `deep_learning/`，使用 PyTorch LSTM 進行智能交易決策。
- **AI 預測**：每天預測該不該持有股票（以台積電為例）。
- **自動交易**：根據預測結果自動買入/賣出。
- **模型架構**：LSTM + 全連接層，使用技術指標作為特徵。
- **完整流程**：數據加載 → 特徵工程 → 模型訓練 → 回測評估。
- **詳細說明**：參考 [deep_learning/README.md](deep_learning/README.md)

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
docker compose run --rm processor python convert_institutional_summary.py
docker compose run --rm importer

# 5. 啟動服務
docker compose up -d backend frontend pgadmin

# 6. 深度學習交易 (新功能 🆕)
cd deep_learning
pip3 install -r requirements.txt
python3 train.py      # 訓練 LSTM 模型
python3 backtest.py   # 回測評估

# 7. 爆量掃描器 (新功能 🆕)
# 方法 A: 使用 CLI 掃描
docker compose run --rm scanner python volume_spike_scanner.py --date 2025-10-03

# 方法 B: 使用 Web UI 掃描
docker compose up -d backend frontend
# 開啟瀏覽器: http://localhost:3000
# 切換到「爆量掃描器」tab → 選擇日期 → 開始掃描
```

## 目錄結構
```
root/
├── scripts/            # 自動化腳本
├── scraper/            # 爬蟲 (Extract)
├── processor/          # 資料清洗 (Transform)
├── importer/           # 資料匯入 (Load)
├── calculator/         # 指標運算
├── scanner/            # 🆕 爆量掃描器
├── backend/            # API 伺服器 (含掃描器 API)
├── frontend/           # 網頁介面 (含掃描器 UI)
├── strategy/           # 交易策略核心
├── backtester/         # 回測系統
├── deep_learning/      # 🆕 深度學習交易系統 (LSTM)
├── common/             # 共用常數與工具
└── data/               # 資料存放區 (Raw/Processed)
```

## 🔍 爆量掃描器使用指南 (Volume Spike Scanner)

### 功能特色

**智能篩選條件:**
- 最小成交量門檻 (預設 500 萬股)
- 爆量倍數檢測 (預設 3 倍 vs 過去 10 日均量)
- 自動過濾長上影線型態 (排除拉高出貨)
- 收盤價須站上 MA60 (季線)，排除弱勢股
- 整合技術指標 (MA、RSI、KD、MACD)

**互動式 K 線圖:**
- 紅漲綠跌 (台灣習慣)
- MA5/10/20/60 均線疊加
- 成交量柱狀圖
- 可縮放、可拖曳

### CLI 使用方式

```bash
# 基本掃描
docker compose run --rm scanner python volume_spike_scanner.py \
  --date 2025-10-03

# 自訂參數
docker compose run --rm scanner python volume_spike_scanner.py \
  --date 2025-10-03 \
  --min-volume 10000000 \
  --volume-ratio 5.0 \
  --avg-days 20 \
  --no-filter-shadow

# 匯出結果
docker compose run --rm scanner python volume_spike_scanner.py \
  --date 2025-10-03 \
  --export results.csv
```

### Web UI 使用方式

1. **啟動服務**
   ```bash
   docker compose up -d backend frontend
   ```

2. **開啟瀏覽器**
   ```
   http://localhost:3000
   ```

3. **使用掃描器**
   - 切換到「爆量掃描器」tab
   - 選擇掃描日期
   - 調整參數 (選填)
   - 點擊「開始掃描」
   - 查看結果並點擊「顯示圖表」

### 遠端訪問設定 (使用 Tailscale)

如需在另一台電腦執行 Frontend 連接此電腦的 Backend：

```bash
# 在另一台電腦上
cd frontend
./start.sh

# 或手動啟動
docker compose up -d
```

詳細設定請參考: [frontend/SETUP_REMOTE.md](frontend/SETUP_REMOTE.md)

### API 端點

**掃描器 API:**
```bash
GET /scanner/volume-spike?date=2025-10-03&min_volume=5000000&volume_ratio=3.0
```

**K線資料 API:**
```bash
GET /scanner/candlestick/{symbol}?date=2025-10-03&days_before=30&days_after=10
```

**API 文件:**
```
http://localhost:8000/docs
```

### 參數說明

| 參數 | 說明 | 預設值 |
|------|------|--------|
| `date` | 掃描日期 (YYYY-MM-DD) | 必填 |
| `min_volume` | 最小成交量 (股) | 5,000,000 |
| `volume_ratio` | 爆量倍數 | 3.0 |
| `avg_days` | 計算平均量天數 | 10 |
| `filter_long_shadow` | 過濾長上影線 | True |

### 實用範例

**案例 1: 尋找超級爆量股 (10倍量)**
```bash
docker compose run --rm scanner python volume_spike_scanner.py \
  --date 2025-10-03 \
  --volume-ratio 10.0
```

**案例 2: 尋找大型股爆量 (億股以上)**
```bash
docker compose run --rm scanner python volume_spike_scanner.py \
  --date 2025-10-03 \
  --min-volume 100000000
```

**案例 3: 包含所有型態 (不過濾上影線)**
```bash
docker compose run --rm scanner python volume_spike_scanner.py \
  --date 2025-10-03 \
  --no-filter-shadow
```

