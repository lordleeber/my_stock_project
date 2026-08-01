# Selection Model 特徵分析 — train_through 2026-05-16

- 模型:`models_selection/2026-05-16/selection_model.pkl`(LGBMRanker ensemble, 10 members, 51 特徵)
- 打分對象:`models_selection/2026-06-11/candidates_scored.csv`(walk-forward 該月生產 picks,378 檔候選)
- SHAP:LightGBM 原生 TreeSHAP(`predict(pred_contrib=True)`),ensemble 成員平均
- 方向(direction_spearman):feature 值 vs 其 SHAP 的 Spearman。+ 單調拉高分數,− 拉低,~0 非單調

### 輸入指紋

兩個輸入都是 gitignored、會被 pipeline 重生的 artifact。同一組日期在不同時間
重跑可能得到完全不同的數字,所以比對兩份報告前先確認指紋是否相同。

- 產出時間:2026-08-01 12:39
- `selection_model.pkl`:md5 `0019dc9aff26` · mtime 2026-07-11 15:51 · 8,886,726 bytes
- `candidates_scored.csv`:md5 `5afeea50bffc` · mtime 2026-07-11 15:52 · 320,970 bytes

同目錄另有封存版本(舊輸入的分析,不會被本工具覆寫):

- [`feature_analysis.backup_2026-07-11_pre_volume_filter.md`](feature_analysis.backup_2026-07-11_pre_volume_filter.md)

## SHAP 全域重要性 + 方向(Top 20)

| feature | gain% | shap% | dir | label |
|---|--:|--:|--:|---|
| rsi6 | 10.27% | 10.92% | +0.97 | strong_up |
| eps_growth_total_pct | 6.02% | 9.82% | +0.97 | strong_up |
| rsi12 | 7.94% | 8.00% | +0.98 | strong_up |
| close_vs_ma240 | 6.77% | 6.45% | +0.83 | strong_up |
| ml_eps_delta_pct | 3.06% | 5.19% | +0.87 | strong_up |
| close_vs_ma5 | 2.03% | 4.29% | -0.93 | strong_down |
| close_vs_ma10 | 1.21% | 3.31% | -0.92 | strong_down |
| margin_usage_ratio | 2.73% | 3.06% | +0.92 | strong_up |
| bb_position | 1.85% | 2.87% | -0.44 | down |
| pe_current | 3.06% | 2.46% | +0.86 | strong_up |
| macd_dif | 2.87% | 2.41% | +0.38 | up |
| pb_ratio | 1.46% | 1.88% | +0.87 | strong_up |
| revenue_cum_yoy | 1.48% | 1.84% | -0.75 | strong_down |
| foreign_streak_days | 0.78% | 1.83% | +0.62 | strong_up |
| revenue_mom_1m | 2.02% | 1.81% | +0.77 | strong_up |
| small_holder_ratio_wow | 1.54% | 1.80% | +0.87 | strong_up |
| revenue_yoy_1m | 2.07% | 1.72% | +0.82 | strong_up |
| close_vs_ma20 | 0.96% | 1.64% | -0.74 | strong_down |
| vol_vs_vma20 | 1.22% | 1.58% | +0.87 | strong_up |
| base_eps_growth_pct | 1.51% | 1.53% | +0.85 | strong_up |

## ⚠️ 方法論注記

- **不可用 picks-vs-pool 中位數推方向**:最終排名是所有特徵 SHAP 的加總,個股可靠其他特徵被拉上來,單一特徵的 picks 中位可能與 pool 中位持平卻仍強單調。
- SHAP 方向在當期候選池上估計,分布外可能不同;Spearman 僅衡量單調性,交互項不完整顯示。

## 跨月 importance 漂移(最近 8 個模型,gain%)

| feature | 2025-11-16 | 2025-12-11 | 2026-01-11 | 2026-02-11 | 2026-03-11 | 2026-04-11 | 2026-05-16 | 2026-06-11 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| rsi6 | 9.54 | 10.52 | 10.94 | 11.50 | 10.80 | 10.74 | 10.27 | 10.37 |
| close_vs_ma240 | 6.81 | 5.81 | 6.86 | 5.89 | 5.72 | 7.03 | 6.77 | 7.39 |
| eps_growth_total_pct | 5.62 | 5.58 | 5.42 | 5.66 | 6.00 | 5.94 | 6.02 | 6.05 |
| rsi12 | 9.04 | 9.18 | 6.23 | 7.22 | 7.84 | 7.92 | 7.94 | 5.97 |
| ml_eps_delta_pct | 3.35 | 3.63 | 3.09 | 3.32 | 3.27 | 3.35 | 3.06 | 3.18 |
| macd_dif | 1.88 | 2.28 | 2.13 | 3.29 | 2.66 | 2.40 | 2.87 | 2.79 |
| pe_current | 1.84 | 1.94 | 2.50 | 2.12 | 2.21 | 2.13 | 3.06 | 2.66 |
| macd_dea | 2.60 | 2.31 | 1.96 | 2.37 | 2.25 | 1.70 | 2.38 | 2.46 |
| margin_usage_ratio | 2.43 | 2.40 | 2.45 | 2.35 | 2.37 | 2.38 | 2.73 | 2.45 |
| revenue_mom_1m | 2.06 | 2.18 | 2.24 | 2.10 | 2.12 | 1.95 | 2.02 | 2.25 |
| close_vs_ma5 | 2.13 | 1.88 | 2.12 | 2.02 | 2.00 | 2.11 | 2.03 | 2.13 |
| revenue_yoy_1m | 2.40 | 2.38 | 2.86 | 2.00 | 2.80 | 2.21 | 2.07 | 2.03 |
