# analysis_codex

`analysis_codex` 採用分版本、可獨立執行的結構：

- `analysis_codex/v1/`
- `analysis_codex/v2/`
- `analysis_codex/v3/`
- `analysis_codex/v4/`

## 版本策略

- `v1` 只作為簡易測試版本（baseline/demo 用途）。
- 後續將不再更新 `v1`，新特徵與新流程只會在 `v2+`（目前為 `v2/v3/v4`）持續迭代。

每個版本都包含：

- `prepare_data.py`
- `train.py`
- `backtest.py`
- `results/`（執行 backtest 後產生）

## 統一原則

1. 主評分指標：`MAE`
2. 輔助指標：`P90_AE`（尾部風險）
3. 訓練目標與主評分指標對齊：`RandomForestRegressor(criterion="absolute_error")`

說明：

- 原則上主評分指標應與訓練目標盡量一致。
- 不同指標過多會增加判讀成本，因此此專案只保留 `MAE + P90_AE`。

## Backtest 輸出

每個版本的 `backtest.py` 只輸出：

- `backtest_by_fold.csv`
- `predictions.csv`

`backtest_summary.csv` 已移除。

## 執行方式

以 v2 為例：

```bash
.\.venv\Scripts\python.exe analysis_codex/v2/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v2/train.py
.\.venv\Scripts\python.exe analysis_codex/v2/backtest.py
```

v1、v3 只要把路徑換成對應版本即可。
v4 也使用同樣流程。
