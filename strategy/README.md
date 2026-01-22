# Strategy Module (核心策略模組)

本模組封裝了所有的量化交易策略邏輯與回測運算引擎。它是本專案的 **Single Source of Truth (單一真理來源)**。

## 設計原則
*   **獨立性**: 不依賴任何特定的 UI (Frontend) 或執行環境 (CLI/Web)。
*   **可重用性**: 同時被 `backend` (Web API) 與 `backtester` (CLI) 呼叫。
*   **參數化**: 所有策略參數 (如持有天數、濾網開關) 皆透過 Config 物件傳遞。

## 模組結構
*   `core.py`: 核心回測引擎。
    *   `StrategyConfig`: 定義回測參數與交易成本。
    *   `run_backtest(df, config)`: 執行回測的主函式。

## 可設定參數 (Strategy Parameters)

| 參數名稱 | 代碼 (`StrategyConfig`) | 說明 | 預設值 |
| :--- | :--- | :--- | :--- |
| **策略模式** | `strategy_mode` | `shares` (固定股數) 或 `amount` (固定金額) | `shares` |
| **每筆資金** | `capital` | 當模式為 `amount` 時，每筆交易投入的資金 | `100,000` |
| **固定股數** | `fixed_shares` | 當模式為 `shares` 時，每筆交易買進的股數 | `1,000` |
| **持有天數** | `hold_days` | 買進後持有的交易日數量 (Time Exit) | `3` |
| **重複加碼** | `allow_pyramiding` | 是否允許在已有持倉時再次買入同一檔股票 | `True` |
| **紅 K 濾網** | `only_red_candle` | 是否限定爆量當天必須收紅 K 才進場 | `False` |
| **停利百分比** | `take_profit_pct` | 設定停利點 (如 0.1 為 10%)。0 表示不啟用 | `0` |
| **停損百分比** | `stop_loss_pct` | 設定停損點 (如 0.05 為 5%)。0 表示不啟用 | `0` |

## 內建策略：量能爆發 (Volume Breakout)

此策略假設「成交量異常放大」代表有主力或法人進場，後續股價容易有波段行情。

### 交易規則
1.  **訊號觸發 (Signal)**:
    *   當日成交量 (`Volume`) > 5 倍的 10日成交量均線 (`VMA10`)。
    *   **紅 K 濾網**: 若啟用，訊號日當天必須收紅 K (`Close > Open`)。
2.  **進場 (Entry)**:
    *   訊號發生日的**下一個交易日開盤價 (Open)** 買進。
3.  **出場 (Exit)**:
    *   **停損停利**: 買入後逐日檢查，若觸發則以收盤價賣出。
    *   **時間出場**: 若未觸發停損停利，則持有 N 天後於收盤價賣出。

### 交易成本 (Transaction Costs)
系統自動計算並扣除台股交易成本：
*   **手續費 (Commission)**: 0.1425% (買進與賣出皆收取)
*   **證交稅 (Tax)**: 0.3% (僅賣出時收取)

## 如何新增策略
1.  在 `core.py` 中修改 `generate_signals` 邏輯或新增新的策略函式。
2.  更新 `StrategyConfig` 及其後的 API/CLI 參數傳遞。