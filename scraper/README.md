# Stock Scraper (股票資料爬取模組)

本模組負責從台灣證券交易所 (TWSE/SII) 與證券櫃檯買賣中心 (TPEx/OTC) 及集保結算所 (TDCC) 抓取各類股票市場資料。

## 核心功能
- **全市場支援**: 同時支援上市 (SII) 與上櫃 (OTC)。
- **日期優先結構**: 輸出目錄為 `raw/category/date=YYYYMMDD/market.csv`，方便資料對齊。
- **輕量化**: 採用 `requests` + `BeautifulSoup`，免 Selenium (特殊需求除外)。
- **MOPS 整合**: 實作公開資訊觀測站 (MOPS) 外資持股與月營收解析。
- **集保股權分散表**: 支援最新一期與歷史資料回補 (自動破解 CSRF Token)。

## 1. 每日行情 (Daily Quotes) 

抓取每日成交資訊、法人買賣超、融資融券等。

### 環境變數
| 變數名稱 | 說明 | 預設值 |
| :--- | :--- | :--- |
| `MARKET_TYPE` | 抓取市場 (`SII`, `OTC`, `ALL`) | `ALL` |
| `START_DATE` | 起始日期 (YYYYMMDD) | 今天 |
| `END_DATE` | 結束日期 (YYYYMMDD) | 今天 |

### Docker 使用方式
```bash
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
# 抓取指定年月 (例如 2025年 3月)
python scraper/fetch_monthly_revenue.py --year 2025 --month 3

# 預設抓取上個月
python scraper/fetch_monthly_revenue.py
```

## 3. 集保股權分散表 (Shareholding Dispersion)

本專案提供兩套工具來處理集保資料：

### A. 全市場每週快照 (Weekly Snapshot)
抓取集保 Open Data 的「最新一期」全市場 CSV。適合每週例行更新。
```bash
python scraper/fetch_tdcc.py
```
輸出：`data/raw/shareholding_div/date=YYYYMMDD/all.csv`

### B. 歷史資料回補 (History Backfill)
針對 Open Data 無法提供的「歷史日期」進行單檔抓取。支援自動繞過 CSRF 防護與連續抓取。

**步驟 1: 產生活躍股票清單**
從最新的月營收報告中，篩選出目前活躍的個股代號 (排除 ETF 與權證)。
```bash
python scraper/generate_active_stocks.py
# 輸出: scraper/active_stocks.txt
```

**步驟 2: 查詢可用日期**
查詢集保網站上可供查詢的歷史日期列表。
```bash
python scraper/fetch_tdcc_history.py --list-dates
```

**步驟 3: 執行批量抓取**
根據清單與指定日期進行抓取。
```bash
python scraper/fetch_tdcc_history.py -f active_stocks.txt -d 20260123
```
輸出：`data/raw/shareholding_div/date=20260123/{stock_id}.csv`

### 歷史資料工具特色
- **自動 Token 管理**: 自動解析並更新 Session Token，防止中斷。
- **斷點續傳**: 自動跳過已存在的檔案 (`.csv`)，失敗可直接重跑。
- **禮貌爬蟲**: 內建隨機延遲 (1~2秒)，避免觸發 WAF。

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
        ├── all.csv        (Open Data 來源)
        ├── 2330.csv       (歷史回補來源)
        └── 2317.csv
```