# analysis_LightGBM

`analysis_LightGBM` 是 LightGBM 路線的實驗目錄。

目前已實作：
- `analysis_LightGBM/v9/t1`
- `analysis_LightGBM/v9/t2`
- `analysis_LightGBM/v9/t3`
- `analysis_LightGBM/v9/compare_with_rf.py`

## 執行方式

```bash
.\.venv\Scripts\python.exe analysis_LightGBM/v9/t1/backtest.py --n-jobs 1
.\.venv\Scripts\python.exe analysis_LightGBM/v9/t2/backtest.py --n-jobs 1
.\.venv\Scripts\python.exe analysis_LightGBM/v9/t3/backtest.py --n-jobs 1
.\.venv\Scripts\python.exe analysis_LightGBM/v9/compare_with_rf.py
```

`compare_with_rf.py` 會輸出：
- `analysis_LightGBM/v9/rf_vs_lgb_compare.csv`
