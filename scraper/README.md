# Stock Scraper (股票資料爬取模組)

本模組負責從台灣證券交易所 (TWSE/SII) 與證券櫃檯買賣中心 (TPEx/OTC) 抓取每日行情、法人買賣超、融資融券及外資持股統計等資料。

## 核心功能
- **全市場支援**: 同時支援上市 (SII) 與上櫃 (OTC)。
- **日期優先結構**: 輸出目錄為 `raw/category/date=YYYYMMDD/market.csv`，方便資料對齊。
- **輕量化**: 採用 `requests` + `BeautifulSoup`，免 Selenium。
- **MOPS 整合**: 實作公開資訊觀測站 (MOPS) 外資持股解析。
- **格式統一**: CSV 強制雙引號包裹、UTF-8-SIG 編碼、自動去除空白。

## 環境變數 (Environment Variables)
| 變數名稱 | 說明 | 預設值 | 範例 |
| :--- | :--- | :--- | :--- |
| `MARKET_TYPE` | 抓取市場 (`SII`, `OTC`, `ALL`) | `ALL` | `OTC` |
| `START_DATE` | 起始日期 (YYYYMMDD) | 今天 | `20230301` |
| `END_DATE` | 結束日期 (YYYYMMDD) | 今天 | `20230301` |
| `FETCH_DELAY` | 請求延遲 (秒) | `3.0` | `5.0` |

## 如何使用 (Docker)

**注意：由於需要包含根目錄的 `common` 模組，建置時請在專案根目錄執行。**

### 1. 編譯映像檔
```bash
docker build -f scraper/Dockerfile -t stock-scraper .
```

### 2. 執行抓取任務
```bash
docker run --rm \
  -v $(pwd)/data:/app/data \
  -e START_DATE=20230301 \
  -e END_DATE=20230301 \
  -e MARKET_TYPE=ALL \
  stock-scraper
```

## 資料目錄結構
```
data/raw/
└── daily_quotes/
    └── date=20230301/
        ├── sii.csv
        └── otc.csv
```
每個 CSV 檔案皆已清理，所有欄位被雙引號 `"` 包裹且編碼為 UTF-8-SIG。
