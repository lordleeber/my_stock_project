# strategyE

蝑 E ?胯TR / 瘜Ｗ?摨西矽?游??拙???

- ???= `entry_open + tp_atr_mult * ATR`
- ????= `entry_open - sl_atr_mult * ATR`
- ?舫 `trail_atr_mult` ??ATR 撠暸??

## Grid Search

```bash
.\.venv\Scripts\python.exe strategies/strategyE/grid_search.py
```

頛詨嚗?- `grid_results_all.csv`
- `grid_results_top20.csv`
- `best_config.json`

## ?桀???蝛粹?

- `atr_lookback`: `3, 5, 7, 10`
- `tp_atr_mult`: `1.0, 1.5, 2.0, 2.5, 3.0`
- `sl_atr_mult`: `1.0, 1.5, 2.0`
- `trail_atr_mult`: `None, 1.0, 1.5, 2.0`
- `max_hold_days`: `10, 12, 15, 20`



