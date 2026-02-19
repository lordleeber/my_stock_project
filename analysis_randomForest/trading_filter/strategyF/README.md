# strategyF

策略 F 是「相對強弱過濾 + 固定出場」：

- 先做橫斷面強弱打分（`upside / delta / volume / confidence`）
- 依 `top_quantile` 只保留強勢標的
- 再套固定停利停損與持有天數

## Grid Search

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyF/grid_search.py
```

輸出：
- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## 目前搜尋空間

- `rs_mode`: `upside_only`, `upside_plus_delta`, `composite`
- `top_quantile`: `0.50, 0.60, 0.70, 0.80`
- `min_upside_ratio`: `1.03, 1.05, 1.08`
- `tp_pct`: `10%, 12%, 14%`
- `sl_pct`: `5%, 7%`
- `trailing_stop_pct`: `None, 5%`
- `max_hold_days`: `12, 15`

