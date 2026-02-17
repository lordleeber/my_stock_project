# EPS Prediction Roadmap

## v5
- 狀態：功能完成
- 目標：改成預測 `delta_eps`，並銜接估值鏈路的誤差評估。
- 已完成：
  - `target` 改為 `delta_eps = Q3 EPS - Q2 EPS`
  - 加入估值誤差指標（`pe_forward`、`target_price`、`upside_pct`）
  - v5.1 加入穩健化（winsorize、hybrid fallback、eps floor）
  - 依回測調參，hybrid 預設 `confidence_quantile` 更新為 `0.95`
- 備註：後續可再做更細緻的分年/分產業調參。

## v6
- 狀態：功能完成
- 目標：固定 `valuation_daily` 欄位與計算鏈路，確保可對接。
- 已完成：
  - 固定欄位映射：`pred_eps -> ttm_eps_forward -> pe_forward -> predict_target_price -> upside_pct`
  - 產出 `valuation_daily_preview.csv`
  - 產出 `valuation_quality_report.json`（檢查 null/inf/覆蓋率）
  - 增加追蹤欄位：`pced_file`、`pced_row`、`pced_col`、`model_version`
  - 加入 hybrid 回退，預設 `confidence_quantile=0.95`
- 後續待辦（現在不做）：
  - market snapshot fallback（9 月無資料時回退到最近可得交易日）
  - `missing_market_snapshot_reason` 診斷欄位

## v7
- 狀態：功能完成（第一版）
- 目標：Regime-aware / 分群建模，改善不同市況下的穩定度。
- 已完成：
  - 新增 regime 切分：`q2_margin` + `rev_volatility`
  - 訓練 global 模型 + regime 子模型（樣本不足則不建）
  - 低信心回退：`regime -> global -> baseline_q2`
  - 回測輸出 `pred_source` 與 `pred_std`，可檢查回退比例
  - 依回測調參，預設 `confidence_quantile` 更新為 `0.95`
- 後續可調：
  - `confidence_quantile`（回退靈敏度）
  - `min_regime_samples`（子模型最小樣本）

## v8
- 目標：事件時間對齊與特徵切片。
- 重點：
  - 只使用「公告當下可得」的特徵
  - 避免任何未來資訊滲漏

## v9
- 目標：不只給點估計，加入區間預測。
- 重點：
  - 產生 `pred_eps_low/mid/high`
  - 同步輸出 `target_price_low/high`、`upside_pct_low/high`

## v10
- 目標：上線化與監控。
- 重點：
  - 定期重訓與版本管理
  - 線上監控（資料品質、預測漂移、策略績效）
  - 回滾機制與告警
