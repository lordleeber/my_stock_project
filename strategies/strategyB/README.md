# strategyB

蝑 B ?臬摰??拙???+ 蝘餃???嚗?脣嚗?
## Grid Search

```bash
.\.venv\Scripts\python.exe strategies/strategyB/grid_search.py
```

頛詨嚗?- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## Optuna Search

```bash
.\.venv\Scripts\python.exe strategies/strategyB/optuna_search.py --n-trials 400 --min-entered-count 100
```

頛詨嚗?- `optuna_results_all.csv`
- `optuna_results_top20.csv`
- `optuna_best_config.json`
- `optuna_study_summary.json`



