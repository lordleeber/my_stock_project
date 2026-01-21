# Stock Analysis Backend (後端 API 服務)

基於 FastAPI 構建的 RESTful API，直接串接 PostgreSQL 資料庫，提供結構化的股票與指標數據。

## 主要 API 端點
- `GET /quotes/top-volume`: 查詢成交量排行榜。
- `GET /analysis/ma`: 查詢股票的移動平均線狀態。
- `GET /analysis/vma`: 查詢股票的成交量均線狀態。
- `GET /health`: 資料庫連線健康檢查。

## 參數支援
所有排行 API 皆支援：
- `date`: 日期 (YYYYMMDD 或 YYYY-MM-DD)。
- `limit`: 回傳筆數。
- `sort`: 排序方向 (`asc` 或 `desc`)。

## 開發者文檔
啟動服務後訪問 `http://localhost:8000/docs` 查看 Swagger 互動式文件。