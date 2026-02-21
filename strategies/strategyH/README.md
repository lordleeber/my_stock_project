# strategyH

策略 H 的核心是「投組層級風險控管」：
- 單檔進出場規則仍用固定停利/停損/可選移動停損/最長持有天數
- 但在進場前，先做投組約束，避免過度集中

## 規則重點
- `max_positions`：最多持有幾檔
- `max_per_industry`：同產業最多幾檔
- `min_volume_lots`：最低日成交量（張）
- `min_upside_ratio`：最低預測上漲比（`predict_target_price / close`）

候選股會先計算分數：
- `score = upside_ratio - 0.3 * pred_delta_std`
- 分數越高越優先，並套用產業上限與總檔數上限

## 檔案
- `strategies/strategyH/grid_search.py`

## 執行方式
```powershell
.\.venv\Scripts\python.exe strategies/strategyH/grid_search.py
```

## 輸出
- `strategies/strategyH/grid_results_all.csv`
- `strategies/strategyH/grid_results_top20.csv`
- `strategies/strategyH/best_config.json`


