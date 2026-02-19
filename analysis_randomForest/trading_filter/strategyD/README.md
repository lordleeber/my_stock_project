# strategyD

策略 D：分批出場（partial take profit + trailing stop）。

核心概念：
- 第一段達標先賣出部分部位。
- 剩餘部位交給 trailing stop 或時間停損。

執行檔：
- `analysis_randomForest/trading_filter/strategyD/grid_search.py`
