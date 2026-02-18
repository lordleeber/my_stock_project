# analysis_codex

`analysis_codex` 是我這條線的版本化實驗目錄，重點是簡單、清晰、可對照。

- `analysis_codex/v1/`
- `analysis_codex/v2/`
- `analysis_codex/v3/`
- `analysis_codex/v4/`
- `analysis_codex/v5/`
- `analysis_codex/v6/`
- `analysis_codex/v7/`
- `analysis_codex/v8/`
  - `analysis_codex/v8/t1/` (8/15 視角)
  - `analysis_codex/v8/t2/` (9月初視角)
  - `analysis_codex/v8/t3/` (10月初視角)
- `analysis_codex/v9/`
  - `analysis_codex/v9/t1/` (8/15 + 特徵工程)
  - `analysis_codex/v9/t2/` (9月初 + 特徵工程)
  - `analysis_codex/v9/t3/` (10月初 + 特徵工程)
- `analysis_codex/v10/` (區間預測版)
  - `analysis_codex/v10/t1/` (8/15 + 區間預測)
  - `analysis_codex/v10/t2/` (9月初 + 區間預測)
  - `analysis_codex/v10/t3/` (10月初 + 區間預測)

## 版本策略

- `v1`：簡易測試版本（baseline/demo），後續不再更新。
- `v2+`：正式迭代版本，依任務目標持續改進。

## 各版本重點

- `v1`：最小可行流程，建立資料、訓練、回測骨架。
- `v2`：加入更多基本特徵與年度展開回測。
- `v3`：補強財務比率特徵（例如現金流、保留盈餘相關比率）。
- `v4`：擴充基本面深度，提升模型對不同公司體質的辨識。
- `v5`：改為預測 `delta_eps`，並同步評估估值鏈路誤差，
  目前 hybrid 預設 `confidence_quantile=0.95`，`n_jobs=-1`。
- `v6`：固定 `pred_eps -> valuation_daily` 鏈路，輸出預覽表與品質報告，
  並加入 hybrid 回退（預設 `confidence_quantile=0.95`，`n_jobs=-1`）。
- `v7`：Regime-aware（分群子模型）+ 低信心回退（global/baseline），
  目前預設 `confidence_quantile=0.95`，`n_jobs=-1`。
- `v8`：事件時點對齊版，嚴格特徵切片為 Q2 + M07/M08（不使用 M09），
  避免使用可能晚於事件時點才可得的欄位。
  - `t1`：Q2 + M07
  - `t2`：Q2 + M07 + M08
  - `t3`：Q2 + M07 + M08 + M09
- `v9`：承接 v8，補強月營收特徵工程（winsorize + 同比 + 產業標準化）。
  - `t1`：Q2 + M07（yoy + industry z）
  - `t2`：Q2 + M07 + M08（yoy + mom + industry z）
  - `t3`：Q2 + M07 + M08 + M09（yoy + mom + industry z）
- `v10`：在 v9_t3 基礎上加入區間預測。
  - `t1/t2/t3` 繼承 v9 的事件切片
  - `pred_rf_delta_low / pred_rf_delta / pred_rf_delta_high`
  - `predict_target_price_low / mid / high`
  - `upside_pct_low / mid / high`
  - 回測輸出 `interval_coverage`、`interval_avg_width`

所有 `v5/v6/v7/v8/v9/v10` 的估值/應用面輸出都套用實務過濾：
- `ttm_eps_forward >= 2.0`
- `日成交量 >= 500 張`（`volume/1000`）

## 近期比較（同條件重跑後）

- `v6` 在 EPS 指標（`MAE`, `P90_AE`）略優於 `v7`
- `v7` 在部分估值誤差（`pe_forward_err_mae`, `target_price_err_mae`）略優
- `v6` 在 `upside_pct_err_mae` 較優

## v8 切片比較（固定樣本）

- `t1`：`MAE=0.6252`, `P90_AE=1.25`
- `t2`：`MAE=0.6357`, `P90_AE=1.28`
- `t3`：`MAE=0.6386`, `P90_AE=1.28`

## v9 切片比較（固定樣本）

- `t1`：`MAE=0.6317`, `P90_AE=1.27`
- `t2`：`MAE=0.6279`, `P90_AE=1.24`
- `t3`：`MAE=0.6272`, `P90_AE=1.243`

解讀：
- v9 已修正 v8 的反直覺現象，加入 8/9 月資訊後（t2/t3）不再劣於 t1。
- 目前最佳是 `t3`（MAE 最低），`t2` 在 P90_AE 最佳。

## v10 切片比較（區間版）

- `t1`：`MAE=0.630`, `P90_AE=1.292`, `coverage=0.258`, `avg_width=0.296`
- `t2`：`MAE=0.628`, `P90_AE=1.272`, `coverage=0.270`, `avg_width=0.294`
- `t3`：`MAE=0.624`, `P90_AE=1.276`, `coverage=0.262`, `avg_width=0.294`

解讀：
- 點估計（MAE）以 `t3` 最佳，尾端誤差（P90）以 `t2` 最佳。
- 目前區間 coverage 約 `0.26`，仍偏低，後續要做區間校準。

## v9 與 v10關係

- `v10` 的資料準備與切片基礎承接 `v9`（同一批特徵工程）。
- `v10` 的新增價值在輸出區間（low/mid/high）與 coverage/width 指標。

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

以 `v8` 三切片為例：

```bash
.\.venv\Scripts\python.exe analysis_codex/v8/t1/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v8/t1/backtest.py
.\.venv\Scripts\python.exe analysis_codex/v8/t2/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v8/t2/backtest.py
.\.venv\Scripts\python.exe analysis_codex/v8/t3/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v8/t3/backtest.py
```

以 `v9` 三切片為例：

```bash
.\.venv\Scripts\python.exe analysis_codex/v9/t1/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v9/t1/backtest.py
.\.venv\Scripts\python.exe analysis_codex/v9/t2/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v9/t2/backtest.py
.\.venv\Scripts\python.exe analysis_codex/v9/t3/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v9/t3/backtest.py
.\.venv\Scripts\python.exe analysis_codex/v9/compare_fixed_universe.py
```

以 `v10` 三切片為例：

```bash
.\.venv\Scripts\python.exe analysis_codex/v10/t1/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v10/t1/backtest.py
.\.venv\Scripts\python.exe analysis_codex/v10/t2/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v10/t2/backtest.py
.\.venv\Scripts\python.exe analysis_codex/v10/t3/prepare_data.py
.\.venv\Scripts\python.exe analysis_codex/v10/t3/backtest.py
```
