# Strategies TODO (v2)

## 目標
- 延續 v1 風險控制成果，解決「成交筆數過低」問題。
- 在不回到 `entry_rule=all` 的前提下，提高策略可交易性與穩定性。
- 提升 optimize 與 backtester 的方向一致性。

## v1 現況（作為 v2 基線）
- 優點：
  - 已禁用 `entry_rule=all`。
  - `2025/09` 的 stop-loss 壓力大幅下降。
- 主要缺口：
  - `2025/05~10` closed trades 從 `294` 降到 `4`，過度保守。
  - 多月出現 `entered_count` 太低，score 退化到懲罰區。

## 範圍（v2）
- 調整 `build_candidates.py` 的濾網強度與分段機制。
- 調整 `optimize_strategy.py` 的評分函數，加入「可交易性目標」。
- 新增診斷輸出與參數掃描報告。
- 不改 `train_eps` 模型訓練流程。

## Step 1: 濾網參數化與掃描
- [ ] 在 `build_candidates.py` 將下列門檻改為可調參數（CLI）
  - `--min-volume-lots`（保留）
  - `--max-atr20-pct`（保留）
  - `--min-foreign-net-20d-lots`（預設先維持 `0`）
  - `--min-inst-net-20d-lots`（預設先維持 `0`）
  - `--min-close-vs-ma60`（預設先維持 `0`）
- [ ] 新增 `--target-candidates-min` 軟下限機制
  - 若過濾後筆數低於下限，依序放寬最嚴格條件（先 atr，再 chip，再 ma60）。
- [ ] 輸出每條件 impact（單條件淘汰筆數 + 累積筆數）。

## Step 2: 候選分層而非單一路徑
- [ ] 在 `trade_candidates.csv` 增加 `tier` 欄位（A/B）
  - Tier A: 嚴格條件
  - Tier B: 放寬條件（僅在 A 不足時補齊）
- [ ] `entry_score` 分段取樣
  - 先取 Tier A top X，再視不足補 Tier B top Y。
- [ ] 仍保留最小必要交易欄位，新增欄位需明確標註為策略內部欄位。

## Step 3: optimize 評分函數升級
- [ ] 新增可交易性目標區間
  - `--target-entered-min`、`--target-entered-max`
  - 低於下限或高於上限都扣分（避免過少/過多）。
- [ ] 將 score 改為多目標
  - `score = return_component - risk_penalty - coverage_penalty`
  - risk 至少包含 `stop_loss_ratio`、`sold_loss_count`。
- [ ] 強制輸出 `score_breakdown` 欄位到 `optimization_results_all.csv`。

## Step 4: 回測對照框架（固定流程）
- [ ] 固定評估區間：`2025/05~10`（與 v1 一致）。
- [ ] 產出以下檔案
  - `before_after_summary_v2.json`
  - `before_after_metrics_v2.csv`
  - `monthly_diagnostics_v2.csv`
- [ ] 增加一致性指標
  - optimize/backtester 同方向月數
  - 月度 `entered_count` 與 `closed_trades_count` 分布

## Step 5: 驗收標準（v2）
- [ ] 不出現 `entry_rule=all`。
- [ ] `weighted_stop_loss_ratio_closed <= 0.35`。
- [ ] `2025/05~10` closed trades 總數至少達到 `30`（先求可交易，再優化）。
- [ ] `range_return_pct_net_closed` 不低於 `0%`。
- [ ] optimize/backtester 同方向月數 >= `4/6`。

## Step 6: 文件更新
- [ ] 更新 `strategies/CLAUDE.md`（新增 v2 參數與 tier 邏輯）。
- [ ] 在 `CLAUDE.md` 補「參數調校順序」建議。
- [ ] 新增 `v2 quickstart` 指令區塊。

## 執行順序（建議）
1. 先做 Step 1（參數化 + impact 輸出）。
2. 再做 Step 3（score 升級），避免只靠濾網硬壓。
3. 接著做 Step 2（tier 補量）。
4. 最後跑 Step 4 驗收並回填 Step 5。
