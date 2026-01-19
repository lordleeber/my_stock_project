# Stock Analysis Backend (股票分析後端 API)

本模組提供基於 FastAPI 的 RESTful API 介面，負責與 PostgreSQL 資料庫互動，並為前端應用程式提供結構化的股票數據。

## 核心功能
- **高性能 API**: 採用 FastAPI 框架，具備非同步 (Async) 處理能力。
- **自動文件**: 內建 Swagger UI (`/docs`) 與 Redoc (`/redoc`)，方便開發者測試。
- **資料庫整合**: 透過 SQLAlchemy 與專案的 PostgreSQL 資料庫連線。
- **健康檢查**: 提供 `/health` 端點監控 API 與資料庫連線狀態。

## 環境變數 (Environment Variables)
| 變數名稱 | 說明 | 預設值 | 範例 |
| :--- | :--- | :--- | :--- |
| `DB_HOST` | 資料庫主機名稱 | `db` | `localhost` |
| `DB_PORT` | 資料庫埠號 | `5432` | `5432` |
| `DB_USER` | 資料庫使用者 | `user` | `user` |
| `DB_PASSWORD` | 資料庫密碼 | `password` | `password` |
| `DB_NAME` | 資料庫名稱 | `stock_db` | `stock_db` |

## 如何使用 (Docker)

### 1. 編譯並啟動服務
建議使用專案根目錄的 `docker-compose.yml` 一鍵啟動：
```bash
docker-compose up --build backend
```

### 2. 存取 API 文件
服務啟動後，可透過瀏覽器訪問：
- **API 根目錄**: `http://localhost:8000/`
- **Swagger 文件**: `http://localhost:8000/docs`
- **連線健康檢查**: `http://localhost:8000/health`

## API 端點 (Endpoints)
- `GET /`: 歡迎訊息。
- `GET /health`: 檢查系統狀態與資料庫連線。
- *(後續擴充)* `GET /quotes/{symbol}`: 查詢特定股票行情。
- *(後續擴充)* `GET /institutional/{date}`: 查詢特定日期法人買賣超。

## 目錄結構
- `main.py`: 應用程式入口點與路由定義。
- `Dockerfile`: 容器化配置文件。
- `requirements.txt`: Python 相依套件列表。
