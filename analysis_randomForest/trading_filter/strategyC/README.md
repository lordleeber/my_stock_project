# strategyC

策略 C 是「進場條件 + 停利停損」的組合搜尋，重點是先用 `entry_rule` 篩掉不符合條件的股票，再做出場管理。

## 參數空間

- `entry_rule.type`: `target_above_entry_ratio` / `pullback_from_ref_close`
- `entry_ratio`:
  - `target_above_entry_ratio`: `1.00 ~ 1.12`（步進 `0.01`）
  - `pullback_from_ref_close`: `0.99 ~ 0.90`（步進 `0.01`）
- `take_profit_rule.type`: `fixed_pct` / `target_price_if_above_entry`
- `fixed_tp_pct`（當 `fixed_pct` 時）: `4% ~ 12%`
- `sl_pct`: `2% ~ 6%`
- `max_hold_days`: `7, 10, 12, 15, 20`

## Grid Search

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyC/grid_search.py
```

輸出：
- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## Optuna Search（新增）

先安裝：

```bash
.\.venv\Scripts\python.exe -m pip install optuna
```

執行（範例 300 trials）：

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyC/optuna_search.py --n-trials 300 --min-entered-count 20
```

輸出：
- `optuna_results_all.csv`
- `optuna_results_top20.csv`
- `optuna_best_config.json`
- `optuna_study_summary.json`

說明：
- `score` 以 `return_percent` 為基礎。
- 若 `entered_count < min_entered_count`，會重罰分數，避免只靠少量交易得到虛高報酬。

