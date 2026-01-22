# Stock Analysis Backend (後端 API 服務)

基於 FastAPI 構建的 RESTful API，直接串接 PostgreSQL 資料庫，提供結構化的股票與指標數據。

> **⚠️ 架構重要說明**:
> 本模組的**回測邏輯 (`/backtest/run`)** 並非直接實作於此，而是呼叫共用的 `strategy` 模組。
> 任何關於交易策略的修改（如進出場規則、訊號定義），請務必修改 `strategy/core.py`，以確保 Web API 與 CLI 工具的行為一致。

## 主要 API 端點
- `GET /quotes/top-volume`: 查詢成交量排行榜。
- `GET /analysis/ma`: 查詢股票的移動平均線狀態。
- `GET /analysis/vma`: 查詢股票的成交量均線狀態。
- `POST /backtest/run`: 執行量化策略回測 (調用 `strategy` 模組)。
- `GET /health`: 資料庫連線健康檢查。

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