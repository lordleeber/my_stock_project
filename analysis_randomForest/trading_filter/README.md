# trading_filter

交易策略實驗區（與模型訓練分離）。

## 目前保留內容

- 單一代表策略：`x9/`
- 策略家族資料夾：`strategyA/` ~ `strategyI/`
- 共用腳本：
  - `build_candidates.py`
  - `cache_daily_quotes.py`
  - `multi_strategy_backtest.py`
- 共用資料：
  - `trade_candidates_2025_1013_1120.csv`
  - `daily_quotes_20251013_1120_sii.csv`

## 已清理

- 先前重複實驗資料夾 `x1~x30` 已刪除（僅保留 `x9`）。

## 關鍵結果檔

- `strategy_compare_x1_x30.csv`：x1~x30 歷史比較結果（保留作為紀錄）
- `strategyA/grid_results_all.csv`：A 類網格搜尋全結果
- `strategyA/grid_results_top20.csv`：A 類前 20 名
- `strategyA/best_config.json`：A 類最佳組合

## strategyA 現況（已完成）

- A 類定義：固定停利停損、全進場、無進場過濾
- 搜尋範圍：
  - `TP = 1%~15%`
  - `SL = 1%~10%`
  - `max_hold_days = 5,7,10,12,15,20,30`
- 最佳結果：
  - `A_tp15_sl10_h15`
  - `total_revenue(損益) = 1175225.72`
  - `return_percent = 5.7205`

## strategyB~I 狀態

- `strategyB/`、`strategyC/`：已建立可執行網格腳本，尚未執行。
- `strategyD/`~`strategyI/`：已建立骨架腳本與說明，尚未實作完整回測流程。
