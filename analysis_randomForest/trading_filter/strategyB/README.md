# strategyB

策略族群 B：固定停利停損 + 移動停損（全進場，無進場過濾）。

## 目標

- 測試在 A 類（固定 TP/SL）之上加入 trailing stop 後，是否能改善報酬/風險。

## 預設搜尋空間

- `tp_pct`: 3% ~ 15%（每 1%）
- `sl_pct`: 2% ~ 10%（每 1%）
- `trailing_stop_pct`: 1% ~ 8%（每 1%）
- `max_hold_days`: 7, 10, 12, 15, 20, 30

## 輸出

- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## 執行（目前先不執行）

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyB/grid_search.py
```
