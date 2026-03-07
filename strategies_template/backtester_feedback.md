# Backtester Feedback Template

## 目的
- 統一記錄策略版本在 backtester 的區間回測結果。
- 讓策略調整不是只憑印象，而是根據固定欄位與固定判讀流程進行。
- 讓每一版 `idea_XX.md` 都能明確對應到上一輪回測回饋。

## 使用時機
- 每完成一版策略實作並跑完主要區間回測後，必須更新一份 feedback 文件。
- 若 `strategies/` 已有正式回饋檔（例如 `strategies/backtester_feedback.md`），則該檔為當前正式版本。
- 本模板提供的是撰寫格式與判讀規則，不直接綁定單一策略版本。

## 建議檔案位置
- 當前實作版本：
  - `strategies/backtester_feedback.md`
- 歷史版本：
  - `strategies_history/<idea_version>/backtester_feedback.md`

## 固定回測口徑
- 部位口徑固定為每檔預算制（預設 `100000`）。
- Main Strategy 與 Baseline 必須使用一致口徑比較。
- 至少要清楚列出：
  - Main Strategy 是哪個版本
  - Baseline 是哪個對照邏輯
  - 回測涵蓋的年月範圍

## 每段區間至少要記錄的數字
- `total_capital`
- `gross_pnl`
- `total_cost`
- `net_pnl`
- `return_pct`
- `sold_count`
- 若可得，也建議加上：
  - `win_count`
  - `loss_count`
  - `avg_pnl_per_trade`
  - `net_pnl / gross_pnl`

## 建議區間
- 若策略跨多年度驗證，至少分開寫：
  - `YYYY-01 ~ YYYY-12`
  - 或實際有資料的完整年度區間
- 若策略剛起始於某年中，可先寫：
  - 例如 `2022-08 ~ 2022-12`
- 不建議只寫全部區間總平均，因為會掩蓋 regime 差異。

## 建議文件結構
1. `總評`
2. `回測口徑`
3. `區間回測摘要`
4. `核心結論`
5. `下一輪調整方向`

## 區間回測摘要寫法（模板）

### `YYYY-MM ~ YYYY-MM`
- Main Strategy
  - `total_capital = ...`
  - `gross_pnl = ...`
  - `total_cost = ...`
  - `net_pnl = ...`
  - `return_pct = ...`
  - `sold_count = ...`
- Baseline
  - `total_capital = ...`
  - `gross_pnl = ...`
  - `total_cost = ...`
  - `net_pnl = ...`
  - `return_pct = ...`
  - `sold_count = ...`
- 判讀
  - Main 是否優於 baseline
  - 問題主要來自：
    - 成本拖累
    - 交易過多
    - 強勢年少賺
    - 弱勢年防守不足

## 固定判讀順序
1. 先看 `return_pct` 是否優於 baseline。
2. 再看 `gross_pnl` 與 `total_cost` 的差距。
3. 若 `gross_pnl` 為正但 `net_pnl` 很薄，優先判定為 cost drag 問題。
4. 若 Main 為正報酬但明顯落後 baseline，優先判定為收益捕捉不足，不可只歸因於成本。
5. 再看 `sold_count` 是否過高或過低：
   - 過高：可能交易過多、邊際交易太多
   - 過低：可能 entry 過嚴、錯過行情

## 核心結論要回答的問題
- 這版策略是否真的比上一版更好？
- 問題主要在：
  - 選股品質
  - 交易成本
  - 進場過嚴
  - 出場過早
  - regime 適應不足
- 下一版是應該：
  - 繼續沿用同一框架微調
  - 還是開新版本 `idea_XX.md`

## 如何銜接到下一版 idea
- 若 feedback 顯示只是小幅參數修正即可解決，可留在同一實作回合。
- 若 feedback 顯示問題屬於策略方向層級，例如：
  - 成本後邏輯需要重寫
  - entry philosophy 要改
  - 需要從 coverage 優先改成 conviction 優先
  - 需要從單一 bucket 改成多 bucket
  則應新建下一版 `idea_XX.md`，不可覆蓋舊檔。

## 禁止事項
- 不可只記「有改善」或「變差」，不附數字。
- 不可只寫總區間，不拆年度或關鍵 regime。
- 不可根據單一年份勝負就直接定論，必須同時看：
  - 報酬
  - 成本
  - 交易數
  - 相對 baseline 的差異
