# strategyI

策略 I 的核心是「信心加權配資」：
- 每檔股票都先算一個信心分數（綜合上漲空間、預測 delta、不確定性）
- 分數越高，單檔投入金額越接近 `max_amount`
- 分數越低，單檔投入金額越接近 `min_amount`

## 規則重點
- 候選池過濾：`min_volume_lots`、`min_upside_ratio`
- 信心分數：
  - `score_raw = 0.6*(upside_ratio-1) + 0.4*pred_rf_delta - std_penalty*pred_delta_std`
  - 再標準化成 `score_norm (0~1)`
- 動態配資：
  - `amount = min_amount + (score_norm^gamma) * (max_amount - min_amount)`

## 檔案
- `analysis_randomForest/trading_filter/strategyI/grid_search.py`

## 執行方式
```powershell
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/strategyI/grid_search.py
```

## 輸出
- `analysis_randomForest/trading_filter/strategyI/grid_results_all.csv`
- `analysis_randomForest/trading_filter/strategyI/grid_results_top20.csv`
- `analysis_randomForest/trading_filter/strategyI/best_config.json`
