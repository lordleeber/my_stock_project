# Stock Analysis Backend (後端 API 服務)

基於 FastAPI 構建的 RESTful API，直接串接 PostgreSQL 資料庫，提供結構化的股票與指標數據。

> **⚠️ 架構重要說明**:
> 本模組的**回測邏輯 (`/backtest/run`)** 並非直接實作於此，而是呼叫共用的 `strategy` 模組。
> 任何關於交易策略的修改（如進出場規則、訊號定義），請務必修改 `strategy/core.py`，以確保 Web API 與 CLI 工具的行為一致。

## 主要 API 端點

### 基礎查詢
- `GET /quotes/top-volume`: 查詢成交量排行榜。
- `GET /analysis/ma`: 查詢股票的移動平均線狀態。
- `GET /analysis/vma`: 查詢股票的成交量均線狀態。
- `GET /health`: 資料庫連線健康檢查。

### 策略與回測
- `POST /backtest/run`: 執行量化策略回測 (調用 `strategy` 模組)。

### 爆量掃描器 🆕
- `GET /scanner/volume-spike`: 掃描異常放量股票。
- `GET /scanner/candlestick/{symbol}`: 取得 K 線圖表資料。

## 參數支援

### 查詢排行 API (GET)
支援日期過濾與排序：
- `date`: 日期 (YYYYMMDD 或 YYYY-MM-DD)。
- `limit`: 回傳筆數。
- `sort`: 排序方向 (`asc` 或 `desc`)。

### 回測 API (POST)
接收 JSON Payload，詳細參數定義請參考 `strategy/README.md` 中的「可設定參數」。

## 開發者文檔
啟動服務後訪問 `http://localhost:8000/docs` 查看 Swagger 互動式文件。
## 🆕 爆量掃描器 API

### 1. 掃描異常放量股票

**端點:** `GET /scanner/volume-spike`

**查詢參數:**
- `date` (必填): 掃描日期，格式 YYYY-MM-DD
- `min_volume` (選填): 最小成交量門檻，預設 5000000 (500萬股)
- `volume_ratio` (選填): 爆量倍數，預設 3.0
- `avg_days` (選填): 計算平均量天數，預設 10
- `filter_long_shadow` (選填): 是否過濾長上影線，預設 true

**回應範例:**
```json
[
  {
    "symbol": "5410",
    "name": "國眾",
    "date": "2025-10-03",
    "open": 37.1,
    "high": 40.1,
    "low": 36.8,
    "close": 39.8,
    "volume": 11792000.0,
    "volume_ratio": 17.59,
    "upper_shadow_ratio": 0.11,
    "ma5": 35.3,
    "ma10": 34.655,
    "ma20": 33.645,
    "ma60": 30.903,
    "rsi6": 89.3,
    "rsi12": 82.38,
    "k": 72.97,
    "d": 61.05
  }
]
```

**使用範例:**
```bash
# 基本掃描
curl "http://localhost:8000/scanner/volume-spike?date=2025-10-03"

# 自訂參數
curl "http://localhost:8000/scanner/volume-spike?date=2025-10-03&min_volume=10000000&volume_ratio=5.0"

# 不過濾上影線
curl "http://localhost:8000/scanner/volume-spike?date=2025-10-03&filter_long_shadow=false"
```

### 2. 取得 K 線圖表資料

**端點:** `GET /scanner/candlestick/{symbol}`

**路徑參數:**
- `symbol`: 股票代號 (如 6548)

**查詢參數:**
- `date` (必填): 中心日期，格式 YYYY-MM-DD
- `days_before` (選填): 向前查詢天數，預設 30
- `days_after` (選填): 向後查詢天數，預設 10

**回應範例:**
```json
[
  {
    "date": "2025-09-03",
    "open": 34.2,
    "high": 34.3,
    "low": 33.9,
    "close": 34.2,
    "volume": 940000.0,
    "ma5": 33.79,
    "ma10": 32.985,
    "ma20": 31.815,
    "ma60": 31.441
  }
]
```

**使用範例:**
```bash
# 基本查詢 (前30後10天)
curl "http://localhost:8000/scanner/candlestick/6548?date=2025-10-03"

# 自訂範圍
curl "http://localhost:8000/scanner/candlestick/6548?date=2025-10-03&days_before=60&days_after=20"
```

## 技術細節

### 掃描邏輯說明

**爆量檢測:**
```sql
-- 計算過去 N 日平均量
AVG(volume) OVER (
    PARTITION BY symbol
    ORDER BY date
    ROWS BETWEEN N PRECEDING AND 1 PRECEDING
) as avg_volume

-- 爆量倍數
volume / avg_volume >= volume_ratio
```

**上影線過濾:**
```sql
-- 上影線比例 = (最高價 - 收盤價) / 實體
upper_shadow_ratio = (high - max(open, close)) / abs(close - open)

-- 過濾條件: 上影線比例 < 1.0 (上影線不可超過實體)
WHERE upper_shadow_ratio < 1.0
```

### 依賴關係

Scanner 端點依賴於：
- `scanner/volume_spike_scanner.py` - 掃描邏輯
- `daily_quotes` 表 - OHLCV 資料
- `technical_indicators` 表 - 技術指標

確保資料庫已執行 `calculator` 計算技術指標。
