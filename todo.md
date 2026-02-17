# EPS Prediction Roadmap

## v5: 增量預測 + 估值誤差一起優化
- 目標：讓 `pred_eps` 對最終 `valuation_daily` 有直接幫助，不只看 EPS 本身。
- 任務：
- 將目標由 `Q3 EPS` 改為 `delta_eps = Q3 - Q2`（或 `residual = Q3 - baseline_q2`）。
- 保留 `baseline_q2_eps`、`baseline_train_median` 作為固定對照。
- 在 backtest 同步評估 EPS 與估值誤差：
  `pe_forward_error`、`target_price_error`、`upside_pct_error`。
- 驗收：
- `year_2025` 優於 baseline。
- `year_2024` 不得明顯退步（需設定可接受門檻）。

## v6: `valuation_daily` 對接與計算流程固定化
- 目標：把 `pred_eps` 穩定映射到 `valuation_daily` 欄位。
- 任務：
- 建立一致流程：`pred_eps -> ttm_eps_forward -> pe_forward -> predict_target_price -> upside_pct`。
- 補上欄位品質檢查（null、inf、極端值）。
- 產出可追溯欄位（資料來源、模型版本、執行日期）。
- 驗收：
- 每日批次可穩定產生 `valuation_daily`，且欄位完整率達標。

## v7: Regime-aware 與回退機制
- 目標：改善模型在特定年份失利的穩定性問題。
- 任務：
- 依市場環境（高波動/低波動、景氣階段）分情境建模或加 regime 特徵。
- 增加低信心回退：低信心樣本直接回退 `baseline_q2_eps`。
- 驗收：
- `year_2024`、`year_2025` 兩個年度至少一項主指標穩定優於或不劣於 baseline。

## v8: 產業分群建模（含樣本數門檻）
- 目標：降低跨產業異質性造成的誤差。
- 任務：
- 實作分產業模型，或加入產業特徵做分層訓練。
- 設定最小樣本數門檻，避免小樣本產業過擬合。
- 比較全市場單一模型 vs 產業分群模型。
- 驗收：
- 分群版本在整體或多數主要產業組別優於單一模型。

## v9: 區間預測（不確定性）
- 目標：提供 `pred_eps` 區間，讓估值與風險可一起判讀。
- 任務：
- 輸出 `pred_eps_low`、`pred_eps_mid`、`pred_eps_high`。
- 推導 `predict_target_price_low/high`、`upside_pct_low/high`。
- 驗收：
- 區間覆蓋率（coverage）達標，且區間寬度不過度膨脹。

## v10: 交易可行性與容量驗證
- 目標：確認訊號可交易，不只是回測數字好看。
- 任務：
- 建立事件回測（以月營收公布日為起點）。
- 納入交易成本、滑價、流動性門檻。
- 評估超額報酬（相對大盤或產業）與訊號容量（可交易筆數/金額）。
- 驗收：
- 風險調整後報酬為正，且容量達到可實際部署門檻。
