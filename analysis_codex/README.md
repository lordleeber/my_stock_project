# analysis_codex

`analysis_codex` 是我這條線的版本化實驗目錄，重點是簡單、清晰、可對照。

- `analysis_codex/v1/`
- `analysis_codex/v2/`
- `analysis_codex/v3/`
- `analysis_codex/v4/`
- `analysis_codex/v5/`
- `analysis_codex/v6/`
- `analysis_codex/v7/`

## 版本策略

- `v1`：簡易測試版本（baseline/demo），後續不再更新。
- `v2+`：正式迭代版本，依任務目標持續改進。

## 各版本重點

- `v1`：最小可行流程，建立資料、訓練、回測骨架。
- `v2`：加入更多基本特徵與年度展開回測。
- `v3`：補強財務比率特徵（例如現金流、保留盈餘相關比率）。
- `v4`：擴充基本面深度，提升模型對不同公司體質的辨識。
- `v5`：改為預測 `delta_eps`，並同步評估估值鏈路誤差。
- `v6`：固定 `pred_eps -> valuation_daily` 鏈路，輸出預覽表與品質報告。
- `v7`：Regime-aware（分群子模型）+ 低信心回退（global/baseline），
  目前預設 `confidence_quantile=0.95`。

## 統一原則

1. 主評分指標固定用 `MAE`。
2. 輔助風險指標用 `P90_AE`（看尾端誤差）。
3. 訓練目標盡量和主評分一致：
   `RandomForestRegressor(criterion="absolute_error")` 對應 MAE 方向。
4. 避免同時堆太多主指標，先把主目標做穩，再看輔助指標。

## Backtest 產物

每個版本的 `backtest.py` 主要產出：

- `backtest_by_fold.csv`
- `predictions.csv`

若版本有估值鏈路，另外輸出：

- `valuation_daily_preview.csv`
- `valuation_quality_report.json`

## 執行方式

以 `v7` 為例：

```bash
.\.venv\Scripts\python.exe analysis_codex/v7/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v7/train.py
.\.venv\Scripts\python.exe analysis_codex/v7/backtest.py
```
