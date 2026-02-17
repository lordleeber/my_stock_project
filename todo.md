# EPS Prediction Roadmap

## v5: 改善 `pred_eps` 核心建模
- 目標：把預測目標改為增量模型，提升相對 `baseline_q2_eps` 的表現。
- 任務：
- 將目標由 `Q3 EPS` 改為 `delta_eps = Q3 - Q2`（或 `residual = Q3 - baseline_q2`）。
- 保留現有 `baseline_q2_eps`、`baseline_train_median` 作為對照。
- 在 `analysis_codex/v5` 建立 `prepare_data.py`、`train.py`、`backtest.py`。
- 指標維持 `MAE + P90_AE`，並確認訓練目標對齊（`criterion="absolute_error"`）。
- 驗收：
- `backtest_by_fold.csv` 中 `rf_vanilla` 的 `MAE` 至少不劣於 `baseline_q2_eps`。

## v6: 對齊 `valuation_daily` 的估值誤差
- 目標：不只看 EPS 誤差，還要降低估值欄位誤差。
- 任務：
- 新增評估欄位：`pe_forward_error`、`target_price_error`、`upside_pct_error`。
- 在 backtest 中同時輸出 EPS 與估值層誤差（fold 級別）。
- 建立從 `pred_eps` 映射到 `ttm_eps_forward -> pe_forward -> predict_target_price` 的一致流程。
- 驗收：
- 在至少 2/3 folds，估值誤差指標優於 baseline。

## v7: 嚴格時點一致（as-of）與資料洩漏防護
- 目標：確保模型只使用「月營收公布當下可得」資訊。
- 任務：
- 在資料準備階段加入 as-of 規則與欄位可得性檢查。
- 為每個特徵標記 `feature_available_date`（或等效邏輯）。
- 加入資料洩漏檢查報告（若有違規欄位直接 fail）。
- 驗收：
- 回測流程可輸出 leakage check 結果，且無違規特徵。

## v8: 產業分群與模型穩健化
- 目標：降低跨產業異質性對 `pred_eps` 的干擾。
- 任務：
- 加入產業欄位，實作「分產業模型」或「產業特徵」。
- 比較全市場單一模型 vs 產業分群模型。
- 加入低信心回退機制（低信心時回退 `baseline_q2_eps`）。
- 驗收：
- 分群版本在整體或多數產業組別優於單一模型。

## v9: 預測區間與風險感知輸出
- 目標：提供 `pred_eps` 區間，讓 `valuation_daily` 能表達不確定性。
- 任務：
- 輸出 `pred_eps_low`、`pred_eps_mid`、`pred_eps_high`。
- 推導 `predict_target_price_low/high`、`upside_pct_low/high`。
- 將區間欄位接入 `valuation_daily` 生成流程。
- 驗收：
- 回測可評估區間覆蓋率（coverage），且區間寬度合理。

## v10: 上線前回測與交易可行性驗證
- 目標：確認訊號具備實際交易價值，而不只統計上好看。
- 任務：
- 建立事件回測（以月營收公布日為事件起點）。
- 納入交易成本、滑價、流動性門檻。
- 以超額報酬（相對大盤或產業）評估訊號有效性。
- 驗收：
- 在回測期間達到正的風險調整後報酬，並通過穩健性檢查。
