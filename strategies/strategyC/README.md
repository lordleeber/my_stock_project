# strategyC

蝑 C ?胯脣璇辣 + ?????蝯???嚗?暺? `entry_rule` 蝭拇?銝泵??隞嗥??∠巨嚗???渡恣??
## ?蝛粹?

- `entry_rule.type`: `target_above_entry_ratio` / `pullback_from_ref_close`
- `entry_ratio`:
  - `target_above_entry_ratio`: `1.00 ~ 1.12`嚗郊??`0.01`嚗?  - `pullback_from_ref_close`: `0.99 ~ 0.90`嚗郊??`0.01`嚗?- `take_profit_rule.type`: `fixed_pct` / `target_price_if_above_entry`
- `fixed_tp_pct`嚗 `fixed_pct` ??: `4% ~ 12%`
- `sl_pct`: `2% ~ 6%`
- `max_hold_days`: `7, 10, 12, 15, 20`

## Grid Search

```bash
.\.venv\Scripts\python.exe strategies/strategyC/grid_search.py
```

頛詨嚗?- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## Optuna Search嚗憓?

??鋆?

```bash
.\.venv\Scripts\python.exe -m pip install optuna
```

?瑁?嚗?靘?300 trials嚗?

```bash
.\.venv\Scripts\python.exe strategies/strategyC/optuna_search.py --n-trials 300 --min-entered-count 20
```

頛詨嚗?- `optuna_results_all.csv`
- `optuna_results_top20.csv`
- `optuna_best_config.json`
- `optuna_study_summary.json`

隤芣?嚗?- `score` 隞?`return_percent` ?箏蝷?- ??`entered_count < min_entered_count`嚗??蔑?嚗????漱???啗?擃?研?


