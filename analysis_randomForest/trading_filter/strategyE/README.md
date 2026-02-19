# strategyE

策略 E 是「ATR / 波動度調整停利停損」：

- 停利價 = `entry_open + tp_atr_mult * ATR`
- 停損價 = `entry_open - sl_atr_mult * ATR`
- 可選 `trail_atr_mult` 做 ATR 尾隨停損

## Grid Search

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyE/grid_search.py
```

輸出：
- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## 目前搜尋空間

- `atr_lookback`: `3, 5, 7, 10`
- `tp_atr_mult`: `1.0, 1.5, 2.0, 2.5, 3.0`
- `sl_atr_mult`: `1.0, 1.5, 2.0`
- `trail_atr_mult`: `None, 1.0, 1.5, 2.0`
- `max_hold_days`: `10, 12, 15, 20`

