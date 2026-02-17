# analysis_codex

`analysis_codex` 採用分版本、可獨立執行的結構：

- `analysis_codex/v1/`
- `analysis_codex/v2/`
- `analysis_codex/v3/`
- `analysis_codex/v4/`
- `analysis_codex/v5/`
- `analysis_codex/v6/`

## 版本策略

- `v1` 只作為簡易測試版本（baseline/demo）。
- 後續不再更新 `v1`。
- 新特徵與新流程主要在 `v2+`（`v2/v3/v4/v5`）持續迭代。

## 各版本重點

- `v1`: 最小可用版，特徵最少，主要做流程驗證與 baseline 對照。
- `v2`: 加入季節性與年增訊號（`ly_q3_eps`, `rev_yoy_m7`），建立年別回測基線。
- `v3`: 加入財務品質與結構特徵（`q2_ocf_ratio`, `q2_re_ratio`）與營收動能。
- `v4`: 擴充更多比率型財務特徵（ROE、負債比、流動比等），強化基本面深度。
- `v5`: 改為預測 `delta_eps`（增量），並同時評估估值誤差
  （`pe_forward_err_mae`, `target_price_err_mae`, `upside_pct_err_mae`）。
- `v6`: 固定化 `pred_eps -> valuation_daily` 鏈路，輸出 `valuation_daily_preview.csv`
  與 `valuation_quality_report.json`（欄位品質與可追溯檢查）。

## 統一原則

1. 主評分指標：`MAE`
2. 輔助指標：`P90_AE`（尾部風險）
3. 訓練目標與主評分指標對齊：`RandomForestRegressor(criterion="absolute_error")`

說明：

- 主評分指標應與訓練目標盡量一致。
- 避免指標過多導致判讀混亂，預設聚焦在 `MAE + P90_AE`。

## Backtest 輸出

每個版本的 `backtest.py` 主要輸出：

- `backtest_by_fold.csv`
- `predictions.csv`

## 執行方式

以 `v5` 為例：

```bash
.\.venv\Scripts\python.exe analysis_codex/v5/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v5/train.py
.\.venv\Scripts\python.exe analysis_codex/v5/backtest.py
```

`v2/v3/v4` 使用相同流程，僅替換版本路徑。
