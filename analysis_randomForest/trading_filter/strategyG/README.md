# strategyG

策略 G 是「依持有天數分段」的 time-regime 出場：

- 前段（`holding_day <= switch_day`）用 `early_tp/early_sl`
- 後段（`holding_day > switch_day`）用 `late_tp/late_sl`
- 可選 `trailing_stop_pct`

## Grid Search

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyG/grid_search.py
```

輸出：
- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## 目前搜尋空間

- `switch_day`: `5, 7, 10`
- `early_tp_pct`: `6%, 8%, 10%`
- `early_sl_pct`: `3%, 5%`
- `late_tp_pct`: `10%, 12%, 14%`
- `late_sl_pct`: `5%, 7%`
- `trailing_stop_pct`: `None, 5%`
- `max_hold_days`: `12, 15, 20`

