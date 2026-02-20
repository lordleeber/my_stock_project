# strategyD

策略 D 是「分批停利 + 其餘部位動態出場」：
- 先在 `tp1_pct` 做第一次部分停利（賣出 `partial_ratio`）
- 剩餘部位再由 `trailing_stop_pct` / `sl_pct` / `tp2_pct` / 時間停損管理

## Grid Search
```powershell
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyD/grid_search.py
```

輸出：
- `analysis_randomForest/trading_filter/strategyD/grid_results_all.csv`
- `analysis_randomForest/trading_filter/strategyD/grid_results_top20.csv`
- `analysis_randomForest/trading_filter/strategyD/best_config.json`

## Optuna Search
```powershell
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyD/optuna_search.py --n-trials 400
```

輸出：
- `analysis_randomForest/trading_filter/strategyD/optuna_results_all.csv`
- `analysis_randomForest/trading_filter/strategyD/optuna_results_top20.csv`
- `analysis_randomForest/trading_filter/strategyD/optuna_best_config.json`
- `analysis_randomForest/trading_filter/strategyD/optuna_study_summary.json`

## 主要參數
- `tp1_pct`: `4% ~ 10%`
- `tp2_pct`: `None / 12% / 14% / 16%`
- `partial_ratio`: `30% / 50% / 70%`
- `sl_pct`: `3% ~ 7%`
- `trailing_stop_pct`: `3% ~ 7%`
- `max_hold_days`: `10 / 12 / 15 / 20`
