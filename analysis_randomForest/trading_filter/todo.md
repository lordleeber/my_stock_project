# trading_filter TODO

## 現況

1. 目錄已精簡：`x1~x30` 僅保留 `x9`。
2. `strategyA` 已完成並已跑完網格搜尋（1050 組）。
3. `strategyB`、`strategyC`：程式已建立，尚未執行。
4. `strategyD`~`strategyI`：骨架已建立，尚未實作完整回測。

## 已完成

1. 建立共用回測引擎：`multi_strategy_backtest.py`
2. 建立日線快取流程：`cache_daily_quotes.py`
3. 完成 `strategyA/grid_search.py` 並輸出：
   - `strategyA/grid_results_all.csv`
   - `strategyA/grid_results_top20.csv`
   - `strategyA/best_config.json`

## 待執行

1. 跑 `strategyB/grid_search.py`（trailing stop 族群）
2. 跑 `strategyC/grid_search.py`（進場過濾 族群）
3. 比較 A/B/C 最佳組合（同一評分標準）

## 待實作

1. `strategyD`：分批出場（partial take profit）
2. `strategyE`：波動度調整 TP/SL（ATR / volatility）
3. `strategyF`：相對強弱進場過濾
4. `strategyG`：時間分段停損停利
5. `strategyH`：組合層風控（開倉數/產業曝險/風險預算）
6. `strategyI`：信心加權倉位

## 原則

1. 優先使用同一份候選與同一份日線快取，確保可比性。
2. 先看 `total_revenue(損益)`，再看 `return_percent`。
3. 排除樣本太少的策略後再排名（避免少量交易造成假象）。
