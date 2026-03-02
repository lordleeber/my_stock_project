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

## Step 0: 前置作業
- [ ] 確認 Python 環境與套件
  - 使用專案虛擬環境：`venv/bin/python`
  - 需可匯入：`pandas`, `numpy`, `sqlalchemy`, `lightgbm`
- [ ] 確認 DB 可連線且必要資料表存在
  - 主要資料表：`daily_quotes`, `technical_indicators`, `institutional_investors`, `quarterly_reports`, `monthly_revenue`
- [ ] 確認模型檔案已發布
  - 模型索引：`models_eps/<year>/<month>/latest.json`
  - `latest.json` 需指向可讀取的 LightGBM 模型檔（通常為 `.pkl`）
- [ ] 確認月份是否為可執行月份
  - `02`、`03` 月不執行本流程（該月暫不訓練/推論）
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`models_eps/2023/08/` 與 `strategies/output/2023/08/`
  - 產出哪些檔案（用途）：
    - `models_eps/2023/08/latest.json`：提供 `predict_published.py` 讀取當月已發布模型。
    - `models_eps/2023/08/*.pkl`：實際模型權重檔，供推論使用。
    - `strategies/output/2023/08/`：策略流程當月輸出目錄（後續 Step 1~Step 4 會在此寫檔）。

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
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`strategies/output/2023/08/`
  - 產出哪些檔案（用途）：
    - `trade_candidates.csv`：套用 v2 參數化濾網後的候選池（作為 optimize/backtester 輸入）。
    - （log）條件 impact 統計：檢查每個過濾條件的淘汰強度與最終保留筆數。

## Step 2: 候選分層而非單一路徑
- [ ] 在 `trade_candidates.csv` 增加 `tier` 欄位（A/B）
  - Tier A: 嚴格條件
  - Tier B: 放寬條件（僅在 A 不足時補齊）
- [ ] `entry_score` 分段取樣
  - 先取 Tier A top X，再視不足補 Tier B top Y。
- [ ] 仍保留最小必要交易欄位，新增欄位需明確標註為策略內部欄位。
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`strategies/output/2023/08/`
  - 產出哪些檔案（用途）：
    - `trade_candidates.csv`：含 tier 分層後的最終候選清單，檢查 Tier A/B 的補量是否正常。

## Step 3: optimize 評分函數升級
- [ ] 新增可交易性目標區間
  - `--target-entered-min`、`--target-entered-max`
  - 低於下限或高於上限都扣分（避免過少/過多）。
- [ ] 將 score 改為多目標
  - `score = return_component - risk_penalty - coverage_penalty`
  - risk 至少包含 `stop_loss_ratio`、`sold_loss_count`。
- [ ] 強制輸出 `score_breakdown` 欄位到 `optimization_results_all.csv`。
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`strategies/output/2023/08/results_optimize/`
  - 產出哪些檔案（用途）：
    - `optimization_results_all.csv`：全部 trial，檢查 `score_breakdown` 與 coverage/risk 懲罰是否生效。
    - `optimization_results_top20.csv`：前 20 名候選策略，做人工對照。
    - `best_strategy.json`：當月最終採用策略參數。
    - `current_month_backtest.csv`：最佳策略套用到當月候選的模擬結果。
    - `optimization_summary.json`：執行摘要（period、trial 數、最佳分數等）。

## Step 4: 回測對照框架（固定流程）
- [ ] 固定評估區間：`2025/05~10`（與 v1 一致）。
- [ ] 產出以下檔案
  - `before_after_summary_v2.json`
  - `before_after_metrics_v2.csv`
  - `monthly_diagnostics_v2.csv`
- [ ] 增加一致性指標
  - optimize/backtester 同方向月數
  - 月度 `entered_count` 與 `closed_trades_count` 分布
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`（單月）+ 區間腳本（多月）
  - 產出的路徑：`backtester/output/2023/08/`（單月）與 `backtester/output/diagnostics/`（區間）
  - 產出哪些檔案（用途）：
    - `trades.csv`：逐筆交易明細（進出場、報酬、exit_reason）。
    - `monthly_summary.csv`：單月聚合績效。
    - `equity_curve.csv`：資金曲線。
    - `summary.json`：單月回測摘要。
    - `before_after_summary_v2.json`：v2 前後比較摘要。
    - `before_after_metrics_v2.csv`：v2 月度前後比較明細。
    - `monthly_diagnostics_v2.csv`：v2 診斷指標（coverage、stop-loss、方向一致性）。

## Step 5: 驗收標準（v2）
- [ ] 不出現 `entry_rule=all`。
- [ ] `weighted_stop_loss_ratio_closed <= 0.35`。
- [ ] `2025/05~10` closed trades 總數至少達到 `30`（先求可交易，再優化）。
- [ ] `range_return_pct_net_closed` 不低於 `0%`。
- [ ] optimize/backtester 同方向月數 >= `4/6`。
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`（單月 sanity check）+ `2025/05~10`（驗收區間）
  - 產出的路徑：`backtester/output/diagnostics/`
  - 產出哪些檔案（用途）：
    - `before_after_summary_v2.json`：總體是否達標（報酬、stop-loss、交易筆數）。
    - `before_after_metrics_v2.csv`：各月份是否達標與差異來源。

## Step 6: 文件更新
- [ ] 更新 `strategies/CLAUDE.md`（新增 v2 參數與 tier 邏輯）。
- [ ] 在 `CLAUDE.md` 補「參數調校順序」建議。
- [ ] 新增 `v2 quickstart` 指令區塊。
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`（重跑整條流程以驗證文件描述與實作一致）
  - 產出的路徑：`strategies/`
  - 產出哪些檔案（用途）：
    - `CLAUDE.md`：v2 規則、參數、調校順序、quickstart 文件。

## 執行順序（建議）
1. 先做 Step 1（參數化 + impact 輸出）。
2. 再做 Step 3（score 升級），避免只靠濾網硬壓。
3. 接著做 Step 2（tier 補量）。
4. 最後跑 Step 4 驗收並回填 Step 5。

## Backtester 如何使用 Strategies 輸出
- 輸入來源路徑：`strategies/output/<year>/<month>/`
- backtester 主要讀取檔案（每月）：
  - `trade_candidates.csv`：候選交易清單，至少包含 `symbol,predict_target_price,close,entry_date`，作為模擬交易輸入。
  - `results_optimize/best_strategy.json`：最佳策略參數（entry/take-profit/exit rules），作為當月回測配置。
- `backtester/run.py` 流程：
  - 先讀 `trade_candidates.csv` 與 `best_strategy.json`。
  - 依 candidates 的 `symbol` 與 `entry_date` 從 DB 讀真實日線。
  - 套用 `best_strategy.json` 規則逐檔模擬，輸出：
    - `backtester/output/<year>/<month>/trades.csv`
    - `backtester/output/<year>/<month>/monthly_summary.csv`
    - `backtester/output/<year>/<month>/equity_curve.csv`
    - `backtester/output/<year>/<month>/summary.json`
- 若任一必要檔案缺失（`trade_candidates.csv` 或 `best_strategy.json`），該月 backtest 會跳過或報錯（依單月/批次腳本行為）。
