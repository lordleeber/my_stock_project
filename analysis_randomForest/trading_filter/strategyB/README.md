# strategyB

策略 B 是固定停利停損 + 移動停損（全進場）。

## Grid Search

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyB/grid_search.py
```

輸出：
- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## Optuna Search

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyB/optuna_search.py --n-trials 400 --min-entered-count 100
```

輸出：
- `optuna_results_all.csv`
- `optuna_results_top20.csv`
- `optuna_best_config.json`
- `optuna_study_summary.json`

