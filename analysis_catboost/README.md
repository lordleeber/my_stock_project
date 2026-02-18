# analysis_catboost

`analysis_catboost` 是 CatBoost 路線的實驗目錄。

目前已實作：
- `analysis_catboost/v9/t1`
- `analysis_catboost/v9/t2`
- `analysis_catboost/v9/t3`
- `analysis_catboost/v9/compare_with_rf_lgb.py`

## 執行方式

```bash
.\.venv\Scripts\python.exe analysis_catboost/v9/t1/backtest.py --n-jobs 1
.\.venv\Scripts\python.exe analysis_catboost/v9/t2/backtest.py --n-jobs 1
.\.venv\Scripts\python.exe analysis_catboost/v9/t3/backtest.py --n-jobs 1
.\.venv\Scripts\python.exe analysis_catboost/v9/compare_with_rf_lgb.py
```

比較輸出：
- `analysis_catboost/v9/rf_lgb_cat_compare.csv`
