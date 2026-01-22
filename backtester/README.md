# Stock Backtester (策略回測模組)

本模組負責執行交易策略的歷史回測，驗證策略在過去市場環境下的表現。

> **⚠️ 架構重要說明**:
> 本模組的**核心回測邏輯**並非直接實作於 `main.py`，而是呼叫共用的 `strategy` 模組。
> 請勿直接在此修改交易規則。任何策略變更應在 `strategy/core.py` 中進行，以確保與 Backend API 行為一致。

## 策略說明
本模組目前使用 **量能爆發 (Volume Breakout)** 策略進行回測。

*   **詳細交易規則、進出場邏輯與資金管理模式**：請參考 [strategy/README.md](../strategy/README.md)

## 如何使用 (Docker)

### 1. 編譯映像檔
```bash
docker build -t stock-backtester ./backtester
```

### 2. 執行回測
回測模組需要連線至資料庫 (`stock_db`) 讀取技術指標與行情資料。請確保資料庫容器已啟動且資料已匯入。

```bash
docker run --rm \
  --network container:stock_db \
  -e DB_HOST=localhost \
  -e DB_USER=user \
  -e DB_PASSWORD=password \
  -e DB_NAME=stock_db \
  stock-backtester
```
*(註：若在 Docker Compose 網路內，DB_HOST 通常設為 `db`)*
