# Stock Scraper (股票資料爬取模組)

本模組負責從台灣證券交易所 (TWSE/SII) 與證券櫃檯買賣中心 (TPEx/OTC) 及集保結算所 (TDCC) 抓取各類股票市場資料。

## 更新頻率
| 資料類型 | 更新頻率 | 說明 |
| :--- | :--- | :--- |
| 每日行情 (daily_quotes 等) | **每日** | 交易日收盤後更新 |
| 集保股權分散表 (shareholding_div) | **每週** | 每週五收盤後更新 |
| 月營收 (monthly_revenue) | **每月** | 每月 10 日前公告上月營收 |

## 核心功能
- **全市場支援**: 同時支援上市 (SII) 與上櫃 (OTC)。
- **日期優先結構**: 輸出目錄為 `raw/category/date=YYYYMMDD/market.csv`，方便資料對齊。
- **輕量化**: 採用 `requests` + `BeautifulSoup`，免 Selenium (特殊需求除外)。
- **MOPS 整合**: 實作公開資訊觀測站 (MOPS) 外資持股與月營收解析。
- **集保股權分散表**: 支援最新一期與歷史資料回補 (自動破解 CSRF Token)。

## Docker Compose 使用方式 (推薦)

根據更新頻率，提供三個獨立的 service：

```bash
# 每日行情 (交易日執行)
START_DATE=20250402 END_DATE=20250402 docker compose run --rm scraper-daily

# 集保股權分散表 (每週五執行)
TDCC_DATE=20250321 docker compose run --rm scraper-weekly

# 月營收 (每月 10 日後執行)
REVENUE_YEAR=2025 REVENUE_MONTH=3 docker compose run --rm scraper-monthly
```

---

## 1. 每日行情 (Daily Quotes)

抓取每日成交資訊、法人買賣超、融資融券等。

### 環境變數
| 變數名稱 | 說明 | 預設值 |
| :--- | :--- | :--- |
| `MARKET_TYPE` | 抓取市場 (`SII`, `OTC`, `ALL`) | `ALL` |
| `START_DATE` | 起始日期 (YYYYMMDD) | 今天 |
| `END_DATE` | 結束日期 (YYYYMMDD) | 今天 |

### 使用方式
```bash
# Docker Compose (推薦)
START_DATE=20250402 END_DATE=20250402 docker compose run --rm scraper-daily

# 原生 Docker
docker run --rm \
  -v $(pwd)/data:/app/data \
  -e START_DATE=20250102 \
  -e END_DATE=20251231 \
  -e MARKET_TYPE=ALL \
  stock-scraper
```

## 2. 月營收 (Monthly Revenue)

抓取上市櫃公司每月營收報告 (`mopsov.twse.com.tw`)。

### 使用方式
```bash
# Docker Compose (推薦)
REVENUE_YEAR=2025 REVENUE_MONTH=3 docker compose run --rm scraper-monthly

# 本機執行
python scraper/fetch_monthly_revenue.py --year 2025 --month 3
```

## 3. 集保股權分散表 (Shareholding Dispersion)

透過 `fetch_tdcc_history.py` 抓取集保網站的歷史股權分散資料。支援自動繞過 CSRF 防護與連續抓取。

### 使用方式
```bash
# Docker Compose (推薦)
TDCC_DATE=20250321 docker compose run --rm scraper-weekly
```

### 手動執行步驟

**步驟 1: 產生活躍股票清單**
從最新的月營收報告中，篩選出目前活躍的個股代號 (排除 ETF 與權證)。
```bash
python scraper/generate_active_stocks.py
# 輸出: active_stocks.txt
```

**步驟 2: 查詢可用日期**
查詢集保網站上可供查詢的歷史日期列表。
```bash
python scraper/fetch_tdcc_history.py --list-dates
```

**步驟 3: 執行批量抓取**
根據清單與指定日期進行抓取。
```bash
python scraper/fetch_tdcc_history.py -f active_stocks.txt -d 20250321
```
輸出：`data/raw/shareholding_div/date=20250321/{stock_id}.csv`

### 工具特色
- **自動 Token 管理**: 自動解析並更新 Session Token，防止中斷。
- **斷點續傳**: 自動跳過已存在的檔案 (`.csv`)，失敗可直接重跑。
- **禮貌爬蟲**: 內建隨機延遲 (1~2秒)，避免觸發 WAF。
- **SSL 驗證選項**: 提供 `--no-verify` 參數，解決部分環境的憑證問題。

## 資料目錄結構
```
data/raw/
├── daily_quotes/
│   └── date=20230301/
│       ├── sii.csv
│       └── otc.csv
├── monthly_revenue/
│   └── date=20230301/
│       └── market.csv
└── shareholding_div/
    └── date=20260123/
        ├── 2330.csv
        └── 2317.csv
```