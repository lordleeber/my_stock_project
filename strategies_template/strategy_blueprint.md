# Strategies Template Strategy Blueprint

## 目標
- 建立可重複執行的策略開發流程：資料準備 -> 候選建構 -> 參數優化 -> 回測驗收。
- 確保最終輸出可直接給 `backtester` 使用，避免缺檔或欄位不一致。

## 範圍（Template）
- 允許替換策略邏輯（因子、過濾規則、評分方式）。
- 固定保留輸出介面（`trade_candidates_<release_yyyymmdd>.csv` + `best_strategy.json`）。
- 不改動 `backtester` 的讀檔契約。
- 每次建立 `strategies/` 新版實作時，都必須明確指定一個既有可運作版本作為 base implementation。
  - 不可從空白目錄直接自由發揮。
  - base implementation 一旦指定，需在本文件或衍生文件中寫清楚來源路徑。

## 目前 Production 規格（strategies）
- Candidates 輸出：
  - `build_candidates.py` 寫入 `strategies/output/<year>/<month>/results_candidates/trade_candidates_<release_yyyymmdd>.csv`
  - `release_yyyymmdd` 規則：`05/08/11` 為 `15` 日，其他月份為 `10` 日
  - 不再使用舊檔名 `trade_candidates.csv`
- Quotes cache 輸出：
  - `cache_daily_quotes.py` 針對 current / historical A / historical B，各自寫回該 period 目錄：
    - `strategies/output/<period_year>/<period_month>/results_quotes_cache/daily_quotes_*.csv`
  - 若目的檔已存在，視為該 period cache 已完成並直接 skip
- Optimize 讀檔：
  - candidates：`<period>/results_candidates/trade_candidates_<release_yyyymmdd>.csv`
  - quotes：`<period>/results_quotes_cache/daily_quotes_*.csv`
  - 優化期間僅使用 historical A / B（去年同月 + 上月），不做當月套用回測
  - 不保留舊路徑 fallback，缺檔直接報錯中止
- 時間切斷（avoid look-ahead）：
  - `optimize_strategy.py` 使用本次執行月份 release date 當 as-of cutoff（例：`2023/08 -> 2023-08-15`）
  - 同一個 cutoff 套用在 historical A / historical B
- Fail-fast：
  - candidates 檔缺失：`FileNotFoundError`
  - quotes cache 缺失：`FileNotFoundError`
  - candidates 存在但 symbol 為空（cache 階段）：`RuntimeError`
- 候選保底：
  - `build_candidates.py` 若篩選後 0 檔，強制放入 `2330`
  - 若連 `2330` 都不存在，直接報錯
- 目標價公式：
  - `predict_target_price = pe_current * ttm_eps_forward_live`
  - 不再使用 `pe_current * predict_target_eps`
- 月份執行：
  - `prepare_data.py` 已移除 `02/03` 月阻擋
  - 批次流程是否失敗，改由前置檔案存在性決定

## 固定慣例（執行前先遵守）
- 不在策略流程中重新訓練 EPS 模型；僅使用已發布模型做推論。
- 策略流程不做 `market` 拆分。
- 除非有明確需求，輸出檔名與欄位契約不可任意更動。

## 月度 entry_date 規則（預設）
- `05`、`08`、`11`：模型於 `15` 日收盤後發布，最早進場日為 `16` 日。
- 其他可執行月份：模型於 `10` 日收盤後發布，最早進場日為 `11` 日。
- `build_candidates` 應以此規則生成該月 `entry_date`（若遇休市，順延至下一交易日）。

## 策略邏輯來源與指定版本
- [ ] 先閱讀 `strategies_template/ideas/` 下既有企劃（`idea_01.md`、`idea_02.md`、`idea_03.md`）。
- [ ] 比較既有企劃的優缺點，提出「更好的策略邏輯」並寫成新檔（不可覆蓋舊檔，需保留歷史）。
  - 檔名規則：`idea_XX.md`（遞增編號）。
  - 新檔最上方必填三段：
    - `參考來源`：列出參考了哪些 `idea_XX.md`。
    - `優缺點比較`：逐一寫出參考版本的優點與缺點。
    - `為何此版更好`：明確說明改進點、預期改善的指標與可能 trade-off。
- [ ] 在本文件明確填寫本次實作採用的策略邏輯檔案（只能填一個）。
- [ ] 若未完成「指定策略邏輯檔案」，不得進入 Step 1。
- 本次指定策略邏輯：`<TO_BE_FILLED_BY_EXECUTOR>`（範例：`strategies_template/ideas/idea_04.md`）。

## 標準 Pipeline（模板建議）
1. `prepare_data`
2. `predict_published`
3. `build_candidates`
4. `cache_daily_quotes`
5. `optimize_strategy`
- 建議提供一鍵腳本（例如 `run_strategy_pipeline.py`）串接以上步驟，並在任一步失敗時中止。

## 實作基底與檔案要求（模板固定）
- `strategies/` 底下至少必須存在以下主腳本：
  - `prepare_data.py`
  - `predict_published.py`
  - `build_candidates.py`
  - `cache_daily_quotes.py`
  - `optimize_strategy.py`
  - `run_strategy_pipeline.py`
- 若 `strategies/` 尚無主腳本，應先從指定 base implementation 複製第一版，再做策略化調整。
- `strategies_template/` 的 batch 腳本只負責逐月呼叫 `strategies/` 主腳本，不負責實作策略邏輯。

## 歷史依賴規則（模板固定）
- 任何月份 `Y/M` 要執行 `optimize_strategy.py` 前，必須先確認以下兩個歷史期間已完整存在：
  - historical A：`Y-1 / M`
  - historical B：`Y / M-1`（若 `M=01` 則為 `Y-1 / 12`）
- 上述兩個歷史期間都必須先完成以下產物：
  - `dataset_model_input.csv`
  - `dataset_strategy.csv`
  - `predictions_published.csv`
  - `results_candidates/trade_candidates_<release_yyyymmdd>.csv`
  - `results_quotes_cache/daily_quotes_*.csv`
- 若 historical A / B 任一缺檔，`cache_daily_quotes.py` 或 `optimize_strategy.py` 必須直接 fail-fast，並在錯誤訊息中明確指出：
  - 缺的是哪個年月
  - 缺的是哪個檔案
- 因此單跑某個月份前，執行者必須先判斷是否需要補跑歷史月份的前置三步：
  1. `prepare_data`
  2. `predict_published`
  3. `build_candidates`

## Batch 腳本規範（固定）
- `strategies_template/` 底下提供 5 個 batch 腳本：
  - `batch_prepare_data.py`
  - `batch_predict_published.py`
  - `batch_build_candidates.py`
  - `batch_cache_daily_quotes.py`
  - `batch_optimize_strategy.py`
- 這 5 個 batch 腳本的月份範圍參數固定使用：
  - `--start_year`
  - `--start_month`
  - `--end_year`
  - `--end_month`
- 上述 4 個參數名稱與語意不准更改（對齊既有操作慣例與排程腳本）。
- 這 5 個 batch 腳本固定留在 `strategies_template/`。
- 執行時由 `strategies_template/batch_xxx.py` 直接呼叫 `strategies/` 底下對應主腳本。
- 因此不需要再把 batch 腳本複製到 `strategies/`。

## Step 0: 前置作業（必填）
- [ ] 確認 Python 環境與套件
  - Python 執行檔：`venv/bin/python`
  - 需可匯入：`pandas`, `numpy`, `sqlalchemy`, `lightgbm`
- [ ] 確認 DB 與資料表
  - 至少可查詢：`daily_quotes`, `technical_indicators`, `institutional_investors`, `quarterly_reports`, `monthly_revenue`
- [ ] 確認模型可讀取
  - `models_eps/<year>/<month>/latest.json` 存在且可指向有效模型檔（例如 `.pkl`）
- [ ] 確認執行月份規則
  - 明確記錄 release date 規則（`05/08/11 -> 15`；其他月份 `-> 10`）
- [ ] 測試
  - 測試參數：`--year 2023 --month 08`
  - 產出路徑：`models_eps/2023/08/`、`strategies_template/output/2023/08/`
  - 產出檔案（用途）：
    - `models_eps/2023/08/latest.json`：模型索引
    - `models_eps/2023/08/*.pkl`：推論模型
    - `strategies_template/output/2023/08/`：策略輸出根目錄
- [ ] 語法驗證
  - 首次建立或大改 `strategies/*.py` 後，必須先做最小語法檢查
  - 建議指令：
    - `python3 -m py_compile strategies/prepare_data.py strategies/predict_published.py strategies/build_candidates.py strategies/cache_daily_quotes.py strategies/optimize_strategy.py strategies/run_strategy_pipeline.py`

## Step 1: 資料集與欄位定義
- [ ] 定義本版策略使用欄位（建議 4~10 個核心欄位）
- [ ] 定義每個欄位口徑、時間對齊方式與缺值處理
- [ ] 輸出模型輸入資料集
- [ ] 測試
  - 測試參數：`--year 2023 --month 08`
  - 產出路徑：`strategies_template/output/2023/08/`
  - 產出檔案（用途）：
    - `dataset_model_input.csv`：供 `predict_published.py` 使用
    - `dataset_strategy.csv`：供候選建構與策略計分使用

## Step 2: 候選建構與硬過濾
- [ ] 實作候選池生成（含必要硬過濾）
- [ ] 輸出過濾前後筆數與各條件 impact
- [ ] 確認最小交易必要欄位完整
- [ ] 缺值處理規則要可追溯（缺值是否剔除、補值或降權）
- [ ] 測試
  - 測試參數：`--year 2023 --month 08`
  - 產出路徑：`strategies_template/output/2023/08/`
  - 產出檔案（用途）：
    - `trade_candidates_raw.csv`：過濾前候選（除錯用）
    - `results_candidates/trade_candidates_20230815.csv`：過濾後候選（後續 optimize/backtester 主輸入）
- [ ] diagnostics 路徑固定
  - `candidates_diagnostics.csv` 固定輸出至：
    - `strategies/output/<year>/<month>/candidates_diagnostics.csv`
  - 不放在 `results_candidates/` 子目錄，避免和主交付檔混淆

## Step 3: 候選排序與選股控制
- [ ] 建立 `entry_score`（可拆解為多個子分數）
- [ ] 設定候選保留策略（top N / top pct / tier）
- [ ] 將必要診斷欄位寫入候選輸出
- [ ] 測試
  - 測試參數：`--year 2023 --month 08`
  - 產出路徑：`strategies_template/output/2023/08/`
  - 產出檔案（用途）：
    - `results_candidates/trade_candidates_20230815.csv`：最終候選清單（至少含 `symbol,predict_target_price,close,entry_date`）
    - `candidates_diagnostics.csv`：分數拆解與篩選診斷

## Step 4: 參數優化（optimize）
- [ ] 禁用明顯不合理策略空間（例如 `entry_rule=all`）
- [ ] 加入風險/可交易性約束（stop-loss、最小成交筆數等）
- [ ] 部位口徑固定為每檔預算制（預設 `100000`），不可使用固定 `1000` 股假設
- [ ] 輸出 Top-K 供人工比對
- [ ] 測試
  - 測試參數：`--year 2023 --month 08`
  - 產出路徑：`strategies_template/output/2023/08/results_optimize/`
  - 產出檔案（用途）：
    - `optimization_results_all.csv`：全部 trial
    - `optimization_results_top20.csv`：前 20 名策略
    - `best_strategy.json`：當月最佳策略（backtester 必要檔）
    - `optimization_summary.json`：優化摘要
- [ ] 執行前檢查 historical 依賴
  - 若 `2023/08` 要 optimize，必須先確認：
    - `2022/08` candidates + quotes 已存在
    - `2023/07` candidates + quotes 已存在
  - 若缺檔，不得硬跑 optimize；應先補跑缺少月份的前置步驟

## Step 5: 回測與對帳
- [ ] 單月回測（sanity check）
- [ ] 區間回測（before/after）
- [ ] 比對 optimize 與 backtester 方向一致性
- [ ] 嚴禁 look-ahead bias（不得用當月資料覆蓋歷史訓練期間）
- [ ] 回測部位口徑固定為每檔預算制（預設 `100000`），且 optimize/backtester 必須一致
- [ ] 測試
  - 測試參數：`--year 2023 --month 08` + 區間參數（例如 `2025/05~2025/10`）
  - 產出路徑：`backtester/output/2023/08/`、`backtester/output/diagnostics/`
  - 產出檔案（用途）：
    - `trades.csv`：逐筆交易
    - `monthly_summary.csv`：單月彙總
    - `equity_curve.csv`：資金曲線
    - `summary.json`：單月摘要
    - `before_after_summary.json`：前後比較摘要
    - `before_after_metrics.csv`：前後比較明細

## Step 6: 文件與交接
- [ ] 更新策略文件（欄位定義、參數、限制、調校順序）
- [ ] 補上失敗排查流程（coverage、exit_reason、stop-loss）
- [ ] 文件需包含最小執行指令（單步 + 一鍵 pipeline）
- [ ] 測試
  - 測試參數：`--year 2023 --month 08`（重跑整條流程）
  - 產出路徑：`strategies_template/`
  - 產出檔案（用途）：
    - `README.md` 或 `CLAUDE.md`：流程與參數說明文件

## 最終驗收（給 Backtester 使用）
- [ ] 每月必要輸入檔完整存在於 `strategies_template/output/<year>/<month>/`
- [ ] `results_candidates/trade_candidates_<release_yyyymmdd>.csv` 欄位檢查通過（至少）：
  - `symbol`, `predict_target_price`, `close`, `entry_date`
- [ ] `results_optimize/best_strategy.json` 可被 `backtester/run.py` 正常讀取
- [ ] 缺檔時有明確錯誤訊息或跳過機制

### Backtester 最低交付檔案（Gate）
1. `strategies_template/output/<year>/<month>/results_candidates/trade_candidates_<release_yyyymmdd>.csv`
2. `strategies_template/output/<year>/<month>/results_optimize/best_strategy.json`

## 執行順序（建議）
1. Step 0 -> Step 1（先確保資料與欄位可用）。
2. Step 2 -> Step 3（先有候選，再做排序與容量控制）。
3. Step 4（固定產出最佳策略與完整 optimize 結果）。
4. Step 5 -> Step 6（回測驗收後再更新文件）。

## 最小驗證流程（模板固定）
1. 先確認 `strategies/` 主腳本已從指定 base implementation 建立完成。
2. 執行 `py_compile`，先排除語法錯誤。
3. 先跑目標月份的：
   - `prepare_data.py`
   - `predict_published.py`
   - `build_candidates.py`
4. 檢查 optimize 所需的 historical A / B 是否已有 candidates。
5. 若 historical A / B 缺候選或缺 quotes，先補跑缺少月份的前置步驟與 cache。
6. 再跑目標月份的：
   - `cache_daily_quotes.py`
   - `optimize_strategy.py`
7. 最後確認兩個 gate 檔案存在：
   - `results_candidates/trade_candidates_<release_yyyymmdd>.csv`
   - `results_optimize/best_strategy.json`

## 失效診斷順序（固定）
1. 先看候選覆蓋是否異常下降（`build_candidates` 的 filter impact）。
2. 再看 `optimization_results_top20.csv` 的 `stop_loss_ratio`、`entered_count`。
3. 檢查 `best_strategy.json` 是否過度嚴格。
4. 最後看 backtester `trades.csv` 的 `exit_reason` 分布。
