> # ⚠️ 封存版本 — 不是現行分析
>
> 現行分析在同目錄的 [`feature_analysis.md`](feature_analysis.md)。本檔是
> **2026-07-11 volume filter(PR #14)之前**那版輸入所做的分析,保留作為紀錄。
>
> ## 為什麼會有兩份
>
> 兩份的 **model date(2026-05-16)和 scored date(2026-06-11)完全相同**,
> 光看標題分不出來 —— 差別在底下的 artifact 被重生過:
>
> | | 本封存檔 | 現行 `feature_analysis.md` |
> |---|---|---|
> | 輸入 artifact | PR #14 之前 | 2026-07-11 15:51-15:52 重訓/重生 |
> | 候選池 | (未記錄) | 378 檔 |
> | 輸入指紋 | 無(產生時工具還沒這功能) | 有,見該檔「輸入指紋」段 |
>
> PR #14 把流動性 filter 從「單日 >500 張」改成「20 日均量 ≥400 張」,候選池組成
> 變了,模型重訓,SHAP 分布跟著變。`models_selection/*/` 底下的 `.pkl` / `.csv`
> 都是 gitignored 的可重生 artifact,被覆寫時不會留下痕跡。
>
> **本檔無法重現** —— 產生它的那版 artifact 已被覆寫且無備份,這份 markdown 是
> 該次分析僅存的紀錄。
>
> ## 結論有變嗎?沒有
>
> 2026-08-01 把本檔 Top 20 的方向逐項對照現行版本:**19/20 的 direction 與 label
> 完全一致**,前段班(rsi6 +0.97、eps_growth_total_pct +0.94→+0.97、close_vs_ma240
> +0.89→+0.83、close_vs_ma5/10 全負)排名與方向都沒動。
>
> 唯一數值變號的是 `macd_hist`(+0.04 → −0.16),但兩者都落在 `non_monotonic`
> 區間(|ρ| ≤ 0.2),是零附近的雜訊而非方向翻轉 —— 與「MACD 對績效中性」的既有
> 結論一致。
>
> **一個容易誤讀的地方:** `small_holder_ratio` 在本檔是 Top 20 內的 −0.82,在現行
> 版本掉到第 25 名(方向沒變,還更強:−0.87);而擠進現行 Top 20 的
> `small_holder_ratio_wow` +0.87 是**另一個特徵**(週變化率)。只比對兩張 Top 20
> 表格會誤以為「散戶比例方向翻了」,實際沒有。要比方向請看完整的
> `shap_directionality.csv`,不要只看 Top 20。
>
> ---
>
# Selection Model 特徵分析 — train_through 2026-05-16

- 模型:`models_selection/2026-05-16/selection_model.pkl`(LGBMRanker ensemble, 10 members, 51 特徵)
- 打分對象:`models_selection/2026-06-11/candidates_scored.csv`(walk-forward 該月生產 picks)
- SHAP:LightGBM 原生 TreeSHAP(`predict(pred_contrib=True)`),ensemble 成員平均
- 方向(direction_spearman):feature 值 vs 其 SHAP 的 Spearman。+ 單調拉高分數,− 拉低,~0 非單調

## SHAP 全域重要性 + 方向(Top 20)

| feature | gain% | shap% | dir | label |
|---|--:|--:|--:|---|
| rsi6 | 10.94% | 12.56% | +0.97 | strong_up |
| eps_growth_total_pct | 5.64% | 8.92% | +0.94 | strong_up |
| close_vs_ma240 | 9.17% | 7.25% | +0.89 | strong_up |
| close_vs_ma5 | 2.09% | 6.69% | -0.95 | strong_down |
| rsi12 | 4.90% | 5.97% | +0.97 | strong_up |
| ml_eps_delta_pct | 3.16% | 4.94% | +0.69 | strong_up |
| close_vs_ma10 | 1.80% | 4.36% | -0.93 | strong_down |
| margin_usage_ratio | 2.38% | 2.91% | +0.91 | strong_up |
| bb_position | 1.83% | 2.66% | -0.34 | down |
| revenue_mom_1m | 2.21% | 2.04% | +0.83 | strong_up |
| macd_dif | 2.70% | 2.00% | +0.45 | up |
| revenue_yoy_1m | 2.14% | 1.85% | +0.85 | strong_up |
| foreign_streak_days | 0.78% | 1.80% | +0.59 | strong_up |
| macd_hist | 1.58% | 1.74% | +0.04 | non_monotonic |
| small_holder_ratio | 1.71% | 1.69% | -0.82 | strong_down |
| pe_current | 2.07% | 1.68% | +0.86 | strong_up |
| vol_vs_vma20 | 1.24% | 1.61% | +0.79 | strong_up |
| close_vs_ma20 | 0.97% | 1.50% | -0.90 | strong_down |
| revenue_cum_yoy | 1.37% | 1.41% | -0.82 | strong_down |
| pb_ratio | 1.34% | 1.22% | +0.82 | strong_up |

## ⚠️ 方法論注記

- **不可用 picks-vs-pool 中位數推方向**:最終排名是所有特徵 SHAP 的加總,個股可靠其他特徵被拉上來,單一特徵的 picks 中位可能與 pool 中位持平卻仍強單調。
- SHAP 方向在當期候選池上估計,分布外可能不同;Spearman 僅衡量單調性,交互項不完整顯示。

## 跨月 importance 漂移(最近 8 個模型,gain%)

| feature | 2025-10-11 | 2025-11-16 | 2025-12-11 | 2026-01-11 | 2026-02-11 | 2026-03-11 | 2026-04-11 | 2026-05-16 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| rsi6 | 8.64 | 9.33 | 9.76 | 9.72 | 10.86 | 9.03 | 9.39 | 10.94 |
| close_vs_ma240 | 8.56 | 7.46 | 7.51 | 5.88 | 6.21 | 9.06 | 9.78 | 9.17 |
| eps_growth_total_pct | 6.80 | 6.87 | 6.37 | 7.42 | 6.23 | 6.13 | 5.87 | 5.64 |
| rsi12 | 5.89 | 4.79 | 6.08 | 6.35 | 5.82 | 5.01 | 5.06 | 4.90 |
| ml_eps_delta_pct | 3.45 | 3.61 | 3.42 | 3.48 | 3.54 | 3.42 | 3.35 | 3.16 |
| macd_dif | 2.31 | 2.09 | 2.54 | 2.47 | 3.24 | 2.88 | 2.55 | 2.70 |
| margin_usage_ratio | 2.44 | 2.41 | 2.33 | 2.60 | 2.46 | 2.48 | 2.35 | 2.38 |
| macd_dea | 2.83 | 2.69 | 2.37 | 2.00 | 2.38 | 2.63 | 2.62 | 2.24 |
| revenue_mom_1m | 2.22 | 2.24 | 2.30 | 2.67 | 2.25 | 2.15 | 2.11 | 2.21 |
| revenue_yoy_1m | 2.30 | 3.11 | 2.08 | 2.36 | 2.06 | 1.89 | 2.08 | 2.14 |
| close_vs_ma5 | 2.11 | 2.36 | 2.14 | 2.03 | 1.97 | 2.26 | 1.93 | 2.09 |
| pe_current | 1.99 | 1.98 | 2.05 | 2.16 | 2.07 | 2.24 | 2.12 | 2.07 |
