# Stock Scraper (股票資料爬取模組)

本模組負責從台灣證券交易所 (TWSE/SII) 與證券櫃檯買賣中心 (TPEx/OTC) 抓取每日行情、法人買賣超、融資融券及外資持股統計等資料。

已完成全面重構，移除 Selenium 依賴，改採純 `requests` + `BeautifulSoup` 實作，極致輕量且高效。

## 核心功能
- **全市場支援**：同時支援上市 (SII) 與上櫃 (OTC) 資料抓取。
- **輕量化架構**：移除 Selenium/Chrome，映像檔大小大幅縮減，啟動速度快。
- **高隱匿性**：內建 Referer 與 Header 偽裝，有效規避防爬機制。
- **MOPS 深度整合**：自動解析公開資訊觀測站 (MOPS) 的 HTML 表格並轉存為標準 CSV。
- **Docker 化**：支援參數化執行，並以非 root 使用者 (appuser) 運行，確保安全性。
- **格式統一**：自解析的 CSV 資料強制使用雙引號包裹，確保格式嚴謹。

## 環境變數 (Environment Variables)
執行時可透過 `-e` 參數傳入以下變數：

| 變數名稱 | 說明 | 預設值 | 範例 |
| :--- | :--- | :--- | :--- |
| `MARKET_TYPE` | 抓取市場類型 (`SII`, `OTC`, `ALL`) | `ALL` | `OTC` |
| `START_DATE` | 抓取起始日期 (YYYYMMDD) | 無 (預設今天) | `20230301` |
| `END_DATE` | 抓取結束日期 (YYYYMMDD) | 無 (預設今天) | `20230305` |
| `FETCH_DELAY` | 每筆請求之間的延遲秒數 | `3.0` | `5.0` |
| `OUTPUT_DIR` | 容器內部的資料存放路徑 | `/app/data` | `/app/data` |

## 資料目錄結構
爬取的資料將自動依市場與類別分類存放：
```
data/
├── raw/
│   ├── sii/
│   │   ├── 每日收盤行情/
│   │   ├── 三大法人買賣金額統計表/
│   │   └── ...
│   └── otc/
│       ├── 每日收盤行情/
│       ├── 外資及陸資投資持股統計/
│       └── ...
```

## 如何使用 (Docker)

### 1. 編譯映像檔
在專案根目錄執行：
```bash
docker build -t stock-scraper ./scraper
```

### 2. 執行抓取任務

**抓取指定日期範圍 (上市 + 上櫃)：**
```bash
docker run --rm \
  -v $(pwd)/data:/app/data \
  -e START_DATE=20230301 \
  -e END_DATE=20230305 \
  -e MARKET_TYPE=ALL \
  stock-scraper
```

**只抓取上櫃 (OTC) 資料：**
```bash
docker run --rm \
  -v $(pwd)/data:/app/data \
  -e START_DATE=20230301 \
  -e END_DATE=20230301 \
  -e MARKET_TYPE=OTC \
  stock-scraper
```

### 3. 多容器並行 (加速補歷史資料)
您可以同時啟動多個容器來分工處理不同年份或季度的資料：

```bash
# Container 1: 負責 1-3 月
docker run -d --name scraper_q1 -v $(pwd)/data:/app/data \
  -e START_DATE=20230101 -e END_DATE=20230331 stock-scraper

# Container 2: 負責 4-6 月
docker run -d --name scraper_q2 -v $(pwd)/data:/app/data \
  -e START_DATE=20230401 -e END_DATE=20230630 stock-scraper
```

## 注意事項
- **IP Rate Limit**：雖然程式已內建延遲，但若開啟過多並行容器，仍可能導致出口 IP 被證交所暫時封鎖。建議單一 IP 的並行數不宜過多。
- **資料格式**：MOPS (外資持股) 的 CSV 欄位會強制加上雙引號 `"`，以符合舊版程式的相容性需求。官方直接下載的 CSV 則保持原樣。