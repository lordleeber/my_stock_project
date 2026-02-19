# strategyC

策略族群 C：有進場過濾（target gate / pullback）+ 固定停利停損（可選目標價停利）。

## 目標

- 測試「先篩選進場」是否能提升勝率與報酬率。

## 預設搜尋空間

- `entry_rule.type`: `target_above_entry_ratio` / `pullback_from_ref_close`
- `entry_ratio`:
  - target gate：1.00 ~ 1.12（每 0.01）
  - pullback：0.99 ~ 0.90（每 0.01）
- `take_profit_rule.type`: `fixed_pct` / `target_price_if_above_entry`
- `fixed_tp_pct`（當使用 fixed_pct）：4% ~ 12%（每 1%）
- `sl_pct`: 2% ~ 6%（每 1%）
- `max_hold_days`: 7, 10, 12, 15, 20

## 輸出

- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## 執行（目前先不執行）

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyC/grid_search.py
```
