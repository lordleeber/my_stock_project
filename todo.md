# EPS Prediction Roadmap

## v5
- 狀態：功能完成
- 目標：改成預測 `delta_eps`，並銜接估值鏈路的誤差評估。
- 已完成：
  - `target` 改為 `delta_eps = Q3 EPS - Q2 EPS`
  - 加入估值誤差指標（`pe_forward`、`target_price`、`upside_pct`）
  - v5.1 加入穩健化（winsorize、hybrid fallback、eps floor）
  - 依回測調參，hybrid 預設 `confidence_quantile` 更新為 `0.95`
- 備註：分年/分產業與事件切片方向已在 `v8/v9` 延伸實作，`v5` 本身不再擴充。

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
  - `min_regime_samples`（子模型最小樣本，尚未系統化調參）

## v8
- 狀態：功能完成（第一版）
- 目標：事件時間對齊與特徵切片。
- 已完成：
  - 建立 `analysis_codex/v8/t1`、`analysis_codex/v8/t2`、`analysis_codex/v8/t3`
  - `t1`: Q2 + M07、`t2`: Q2 + M07 + M08、`t3`: Q2 + M07 + M08 + M09
  - 保留 v6 對接輸出鏈路（`valuation_daily_preview` / `quality_report`）
- 後續可調：
  - 事件日定義精緻化（依實際公告日而非固定切點）
  - 加入公告延遲/修正的資料品質處理

## v9
- 狀態：功能完成（第一版）
- 目標：月營收特徵工程強化（承接 v8 的 t1/t2/t3）。
- 已完成：
  - 建立 `analysis_codex/v9/t1`、`analysis_codex/v9/t2`、`analysis_codex/v9/t3`
  - 對 `M07/M08/M09` 做一致化特徵工程：
    - winsorize（訓練集分位數）
    - 同比特徵（yoy）
    - 月動能（mom）
    - 產業標準化（industry z-score）
  - 在固定同一批樣本（`fold + symbol`）下比較 `t1/t2/t3`
  - 比較結果：`t2/t3` 已不再劣於 `t1`（方向合理化）
- 後續可調：
  - industry z-score 以外，再測 rank/quantile 轉換
  - 針對 2025 高波動年度做分年參數

## v10
- 狀態：功能完成（第一版）
- 目標：不只給點估計，加入區間預測。
- 已完成：
  - 建立 `analysis_codex/v10/t1`、`analysis_codex/v10/t2`、`analysis_codex/v10/t3`
  - `t1/t2/t3` 繼承 v9 切片架構並加入區間輸出
  - 產生 `pred_rf_delta_low / mid / high`
  - 同步輸出 `predict_target_price_low/high`、`upside_pct_low/high`
  - 回測新增區間指標：`interval_coverage`、`interval_avg_width`
- 後續可調：
  - 校準區間分位數（目前 0.2/0.8）
  - 目標 coverage 校準（例如 60%/70%/80%）

## v11
- 目標：上線化與監控。
- 重點：
  - 定期重訓與版本管理
  - 線上監控（資料品質、預測漂移、策略績效）
  - 回滾機制與告警
