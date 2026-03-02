# Strategies TODO (v1)

## 目標
- 把籌碼面/技術面資訊納入策略決策，避免再出現 `entry_rule=all` 導致全市場無差別進場。
- 讓 optimize 選出的策略在 backtester（真實行情）上更穩定，優先降低大量 stop loss。

## 範圍（先做 v1）
- 調整 `build_candidates.py`：加入必要因子與硬過濾。
- 調整 `optimize_strategy.py`：限制策略空間 + 風險約束。
- 不改動模型訓練流程（`train_eps`）與 API。

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
    - `strategies/output/2023/08/`：策略流程當月輸出目錄（後續 Step 1~Step 5 會在此寫檔）。

## Step 1: 定義 v1 使用欄位
- [x] 盤點可直接從 DB 取得且穩定的欄位（先 4~6 個）
  - 例：`foreign_net_buy_20d`, `inst_net_buy_20d`, `close_vs_ma60`, `atr20_pct`, `volume_lots`
- [x] 明確每個欄位的計算口徑與缺值處理
  - 缺值預設：不進場（先保守）
  - 已實作口徑：
    - `close_vs_ma60 = q3_close / ma60 - 1`
    - `atr20_pct = atr20 / close * 100`（`atr20` 由 `daily_quotes` 計算 TR 的 20 日均值）
    - `foreign_net_20d_lots = rolling_sum20(foreign_net) / 1000`
    - `inst_net_20d_lots = rolling_sum20(trust_net + dealer_net) / 1000`
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`strategies/output/2023/08/`
  - 產出哪些檔案（用途）：
    - `dataset_model_input.csv`：提供 `predict_published.py` 的模型輸入特徵。
    - `dataset_strategy.csv`：提供 `build_candidates.py` 合成 forward EPS/price 與候選過濾欄位。

## Step 2: build_candidates 納入硬過濾
- [x] 在 `build_candidates.py` 加入硬性條件（v1）
  - `volume_lots >= 200`
  - `ttm_eps_forward_live >= ttm_eps_official_live`
  - `close > ma60`
  - `foreign_net_buy_20d > 0`
  - `inst_net_buy_20d > 0`
  - `atr20_pct <= threshold`（threshold 先用固定值，後續可優化）
- [x] 輸出過濾前/後筆數統計到 log（方便診斷）
  - `2025/09` 驗證：`861 -> 73`（逐步篩選統計已輸出）
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`strategies/output/2023/08/`
  - 產出哪些檔案（用途）：
    - `trade_candidates.csv`：策略實際進場候選清單（最小欄位：`symbol,predict_target_price,close,entry_date`）。

## Step 3: 候選排序分數（entry_score）
- [x] 在 `build_candidates.py` 產生 `entry_score`
  - `entry_score = pred_upside_z + chip_score + tech_score - vol_penalty`
- [x] 每月只保留 `entry_score` 前段（例如 top 20% 或 top N）
  - 已加參數 `--top-entry-score-pct`（`1.0` 代表先不截斷）
- [ ] 把分數拆解欄位寫進 `trade_candidates.csv`（便於追蹤）
  - 目前 `trade_candidates.csv` 仍維持「最小欄位版」，分數僅用於內部篩選
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`strategies/output/2023/08/`
  - 產出哪些檔案（用途）：
    - `trade_candidates.csv`：套用 `entry_score` 排序/篩選後的最終候選池（供後續 cache/optimize 使用）。

## Step 4: optimize 限制策略空間
- [x] 在 `optimize_strategy.py` 禁用 `entry_rule=all`
- [x] 增加穩健性約束（至少一項）
  - 最小成交筆數（避免只成交 1~2 筆）
  - `stop_loss` 比率上限
  - 對高回撤配置加懲罰
- [x] 保留最佳策略同時輸出次佳策略（Top-K）供比對
  - 已新增：
    - `--max-stop-loss-ratio` 參數（預設 `0.5`）
    - trial 結果新增 `stop_loss_count` / `stop_loss_ratio`
    - `score` 會對超過 `max_stop_loss_ratio` 的配置加懲罰
  - `optimization_results_top20.csv` 持續保留 Top-K 比對
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`strategies/output/2023/08/results_optimize/`
  - 產出哪些檔案（用途）：
    - `optimization_results_all.csv`：全部 trial 結果，檢查 score/風險指標分布。
    - `optimization_results_top20.csv`：前 20 名候選策略，做人工對照。
    - `best_strategy.json`：當月最終採用策略參數。
    - `current_month_backtest.csv`：最佳策略套用到當月候選的模擬結果。
    - `optimization_summary.json`：執行摘要（period、trial 數、最佳分數等）。

## Step 5: 回測與對帳
- [x] 回測 `2025/05~2025/10`，確認是否改善 `2025/09` 大量停損問題
- [x] 產出 before/after 指標
  - `return_pct_net_closed`
  - `stop_loss_ratio`
  - `closed_trades_count`
  - `max_drawdown`（若已有）
  - 本次結果（`backtester/output/diagnostics/202505_202510/before_after_summary.json`）：
    - before: `total_net_pnl=-870,538.92`, `range_return_pct=-2.562%`, `closed_trades=294`, `weighted_stop_loss_ratio=0.5136`
    - after:  `total_net_pnl=+4,087.42`, `range_return_pct=+1.636%`, `closed_trades=4`, `weighted_stop_loss_ratio=0.25`
    - 改善方向成立，但成交筆數大幅下降（過濾偏嚴，需在下一步調校）
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`
  - 產出的路徑：`backtester/output/2023/08/`（單月）與 `backtester/output/diagnostics/`（區間對照）
  - 產出哪些檔案（用途）：
    - `trades.csv`：逐筆交易明細（進出場、報酬、exit_reason）。
    - `monthly_summary.csv`：單月聚合績效。
    - `equity_curve.csv`：資金曲線。
    - `summary.json`：單月回測摘要。
    - `before_after_summary.json`：區間前後比較摘要（若有執行 before/after 對照）。

## Step 6: 文件與操作流程
- [ ] 更新 `strategies/CLAUDE.md`
  - 新欄位定義
  - 新過濾邏輯
  - 參數說明
- [ ] 補一段「診斷流程」
  - 當月績效差時，先看 `exit_reason` 分布與 entry coverage
- [ ] 測試
  - 測試時要用的參數：`--year 2023 --month 08`（重跑整條流程以驗證文件描述與實作一致）
  - 產出的路徑：`strategies/`
  - 產出哪些檔案（用途）：
    - `CLAUDE.md`：策略流程、參數與診斷規範文件（給後續維護與執行使用）。

## 驗收標準（v1）
- [x] 不再出現 `entry_rule=all` 作為最佳策略
- [x] `2025/09` 的 `stop_loss` 佔比明顯下降
- [ ] 月度成交筆數不再長期趨近 0（避免過嚴濾網）
- [ ] backtester 與 optimize 的方向一致性提升（至少同方向月數增加）

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
