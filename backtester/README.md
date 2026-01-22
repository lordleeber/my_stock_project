# Stock Backtester (策略回測模組)

本模組負責執行交易策略的歷史回測，驗證策略在過去市場環境下的表現。

> **⚠️ 架構重要說明**:
> 本模組的**核心回測邏輯**並非直接實作於 `main.py`，而是呼叫共用的 `strategy` 模組。
> 請勿直接在此修改交易規則。任何策略變更應在 `strategy/core.py` 中進行，以確保與 Backend API 行為一致。

## 策略說明：量能爆發 (Volume Breakout)

此策略假設「成交量異常放大」代表有主力或法人進場，後續股價容易有波段行情。

### 交易規則
1.  **訊號觸發 (Signal)**:
    *   當日成交量 (`Volume`) > 5 倍的 10日成交量均線 (`VMA10`)。
    *   **紅 K 濾網 (Red Candle Filter)**: 訊號日當天必須收紅 K (`Close > Open`)。
2.  **進場 (Entry)**:
    *   訊號發生日的**下一個交易日開盤價 (Open)** 買進。
3.  **出場 (Exit)**:
    *   買進後持有 3 個交易日，於**第 3 天的收盤價 (Close)** 賣出。
    *   *(相當於訊號日的 T+4 收盤價)*

### 資金管理 (Position Sizing)
目前支援兩種模式：
1.  **固定股數 (Fixed Shares)**: 每筆交易固定買進 1,000 股 (1 張)。
2.  **固定金額 (Fixed Amount)**: 每筆交易投入固定資金 (預設 NT$ 100,000)，計算可買最大股數 (無條件捨去)。

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

## 待實作功能 (Future Work)
- [ ] **停損停利機制**: 設定固定百分比的停損 (Stop Loss) 與停利 (Take Profit)。
- [ ] **手續費與證交稅**: 加入交易成本計算 (目前回測未扣除成本)。
- [ ] **參數最佳化**: 自動尋找最佳的倍數 (如 3倍、5倍) 與持有天數。
