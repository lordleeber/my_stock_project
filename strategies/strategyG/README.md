# strategyG

蝑 G ?胯???憭拇?挾?? time-regime ?箏嚗?
- ?挾嚗holding_day <= switch_day`嚗 `early_tp/early_sl`
- 敺挾嚗holding_day > switch_day`嚗 `late_tp/late_sl`
- ?舫 `trailing_stop_pct`

## Grid Search

```bash
.\.venv\Scripts\python.exe strategies/strategyG/grid_search.py
```

頛詨嚗?- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## ?桀???蝛粹?

- `switch_day`: `5, 7, 10`
- `early_tp_pct`: `6%, 8%, 10%`
- `early_sl_pct`: `3%, 5%`
- `late_tp_pct`: `10%, 12%, 14%`
- `late_sl_pct`: `5%, 7%`
- `trailing_stop_pct`: `None, 5%`
- `max_hold_days`: `12, 15, 20`



