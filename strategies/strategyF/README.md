# strategyF

蝑 F ?胯撠撥撘梢?瞈?+ ?箏??箏??

- ??璈急?Ｗ撥撘望???`upside / delta / volume / confidence`嚗?- 靘?`top_quantile` ?芯??撥?Ｘ???- ???箏???????予??
## Grid Search

```bash
.\.venv\Scripts\python.exe strategies/strategyF/grid_search.py
```

頛詨嚗?- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## ?桀???蝛粹?

- `rs_mode`: `upside_only`, `upside_plus_delta`, `composite`
- `top_quantile`: `0.50, 0.60, 0.70, 0.80`
- `min_upside_ratio`: `1.03, 1.05, 1.08`
- `tp_pct`: `10%, 12%, 14%`
- `sl_pct`: `5%, 7%`
- `trailing_stop_pct`: `None, 5%`
- `max_hold_days`: `12, 15`



