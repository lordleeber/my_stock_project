# strategyD

策略 D 是「分批停利 + 尾隨停損」：

- 先在 `tp1_pct` 觸發時賣出 `partial_ratio` 部位
- 剩餘部位用 `trailing_stop_pct` 與 `sl_pct` 管理
- 可選擇 `tp2_pct` 作為第二段停利（`None` 代表不用第二段停利）

## Grid Search

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyD/grid_search.py
```

輸出：
- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## 目前搜尋空間

- `tp1_pct`: `4%, 6%, 8%, 10%`
- `tp2_pct`: `None, 12%, 14%, 16%`
- `partial_ratio`: `30%, 50%, 70%`
- `sl_pct`: `3%, 5%, 7%`
- `trailing_stop_pct`: `3%, 5%, 7%`
- `max_hold_days`: `10, 12, 15, 20`

