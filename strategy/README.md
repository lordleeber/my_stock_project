# Strategy Module (核心策略模組)

本模組封裝了所有的量化交易策略邏輯與回測運算引擎。它是本專案的 **Single Source of Truth (單一真理來源)**。

## 設計原則
*   **獨立性**: 不依賴任何特定的 UI (Frontend) 或執行環境 (CLI/Web)。
*   **可重用性**: 同時被 `backend` (Web API) 與 `backtester` (CLI) 呼叫。
*   **參數化**: 所有策略參數 (如持有天數、濾網開關) 皆透過 Config 物件傳遞。

## 模組結構
*   `core.py`: 核心回測引擎。
    *   `StrategyConfig`: 定義回測參數。
    *   `run_backtest(df, config)`: 執行回測的主函式。

## 如何新增策略
1.  在 `core.py` 中修改 `generate_signals` 邏輯或新增新的策略函式。
2.  更新 `StrategyConfig` 以支援新策略所需的參數。
3.  同時更新 `backend` 與 `backtester` 以傳遞新參數。
