# Backtester 實作計畫

## 目標
在 `backtester/` 使用真實歷史資料做 walk-forward 回測：
每個月份只用當時可得的策略輸出（候選股 + 最佳參數）做交易模擬，最後輸出月度與全期間績效。

## Phase 1: 規格定義（先鎖契約）
- [x] 定義輸入來源：`strategies/output/<year>/<month>/trade_candidates.csv`
- [x] 定義參數來源：`strategies/output/<year>/<month>/results_optimize/best_strategy.json`
- [x] 定義輸出目錄：`backtester/output/<start>_<end>/`
- [x] 定義必要輸出檔：
  - `trades.csv`
  - `monthly_summary.csv`
  - `equity_curve.csv`
  - `summary.json`

## Phase 2: 資料層（DB 真實行情）
- [x] 建立 `data_loader.py`：直接從 DB 讀 `daily_quotes`
- [x] 提供按 symbol + date range 抓取行情的函式
- [x] 建立交易日工具：
  - 下一個交易日
  - 區間交易日列表
- [x] 建立資料品質處理：缺 open/high/low/close 的規則

## Phase 3: 交易引擎
- [x] 建立 `engine.py` 單筆模擬函式（沿用 strategies 核心邏輯）
- [x] 進場規則：`entry_date` 不可交易則順延到下一交易日 open
- [x] 出場規則：stop loss / take profit / trailing / max_hold_days
- [x] 成本模型（可配置）：手續費、證交稅、滑價
- [x] 輸出完整交易欄位：entry/exit/return/pnl/exit_reason

## Phase 4: 月度 Walk-forward 執行
- [x] 建立 `run.py`：支援單月 `--year --month`，批次由 `batch_run.py` 逐月執行
- [x] 逐月讀取該月候選股與最佳策略參數
- [x] 逐月查行情並執行模擬
- [x] 彙整月度結果與全期間結果
- [x] 對 2/3 月等無候選月份標記 `skipped`

## Phase 5: 防前視偏誤檢查（必做）
- [x] 僅使用該月 `trade_candidates` 與 `best_strategy`
- [x] 禁止讀取未來月份檔案
- [x] 確保交易使用的行情日期 >= 訊號日期
- [x] 檢查失敗時直接 fail

## Phase 6: 驗證與上線
- [x] 單月對帳：結果對齊 `current_month_backtest.csv`（同參數下合理接近）
- [x] 12 個月 smoke test（不中斷）
- [x] 輸出統計檢查：交易數、勝率、MDD、累積報酬
- [x] 補上 README/操作指令

## 建議實作順序（最短路徑）
1. 先做單月可跑通版本（Phase 2 + 3 + 單月 run）。
2. 再做多月 walk-forward（Phase 4）。
3. 最後補完整報表與防前視檢查（Phase 5 + 6）。
