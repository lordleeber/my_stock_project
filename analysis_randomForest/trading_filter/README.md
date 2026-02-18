# trading_filter

這個資料夾專門放「交易/估值篩選」與「簡單交易回測」，避免和模型訓練/回測混在一起。

## 資料來源

- `analysis_randomForest/v10/t3/results/predictions_year_2025.csv`
- `analysis_randomForest/v10/t3/dataset.csv`

## Live 估值口徑（你指定）

- `ttm_eps_official_live = previous_q3 + prev_q4 + q1 + q2_official`
- `ttm_forward_live = prev_q4 + q1 + q2_official + predict_q3_eps`
- `predict_q3_eps = q2_eps + pred_rf_delta`

## 候選股篩選條件

- `ttm_eps_forward_live >= 2.0`
- `volume / 1000 >= 500`（至少 500 張）
- `ttm_eps_forward_live >= ttm_eps_official_live`

## 交易回測規則（目前版本）

- `2025-10-13` 開盤買進 1 張
- 盤中碰到 `predict_target_price` 即賣出
- 盤中跌到買價 `-5%` 即停損賣出
- 統計區間到 `2025-11-20`
- 若到期未觸發，記錄 `open_until_end`

## 輸出檔案

- `trade_candidates_2025_1013_1120.csv`
- `results/trade_backtest_20251013_1120_all.csv`
- `results/trade_backtest_20251013_1120_sold.csv`
- `results/trade_backtest_20251013_1120_open_until_end.csv`
- `results/trade_backtest_20251013_1120_summary.json`

所有數值欄位統一四捨五入到小數第 2 位。

## 執行方式

```bash
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/build_candidates.py
.\.venv\Scripts\python.exe analysis_randomForest/trading_filter/trade_backtest_20251013.py
```
