# Idea 02: 可交易性優先的規則式策略（v2）

## 參考來源
- `idea_01.md`（規則式多因子策略 v1）

## 優缺點比較
- `idea_01.md` 優點：
  - 規則清楚、可解釋性高。
  - 風險控制方向正確（可抑制無差別進場與高停損）。
- `idea_01.md` 缺點：
  - 過濾條件偏硬，容易造成候選與成交筆數過低。
  - 在不同市場狀態下彈性不足，覆蓋率波動大。

## 為何此版更好
- 把關鍵門檻參數化，讓策略可以隨市場環境調整鬆緊。
- 新增候選下限與 Tier 補量機制，降低「幾乎無交易」風險。
- 在優化目標中加入 coverage 懲罰，避免只追求低風險而犧牲可交易性。
- 預期改善：
  - `entered_count` 與 `closed_trades_count` 回到可用區間。
  - 維持 stop-loss 控制，不回退到 `entry_rule=all`。
- 主要 trade-off：
  - 規則與參數數量增加，調參複雜度上升。
  - 候選變多可能引入部分低品質交易，需靠多目標評分抑制。

## 策略定位
- 類型：在 v1 基礎上的參數化規則策略。
- 核心目標：在維持風險控制前提下，修正交易筆數過低問題。

## 主要邏輯
- 保留 v1 的多因子框架（EPS、籌碼、趨勢、波動、流動性）。
- 把硬門檻改成可調參數，讓策略可以按市場環境調節鬆緊。

## 參數化過濾
- 核心可調門檻：
  - `min_volume_lots`
  - `max_atr20_pct`
  - `min_foreign_net_20d_lots`
  - `min_inst_net_20d_lots`
  - `min_close_vs_ma60`
- 設置候選下限 `target_candidates_min`：
  - 若候選不足，按順序放寬條件（ATR -> 籌碼 -> 趨勢）。

## 分層補量邏輯
- Tier A：嚴格條件候選。
- Tier B：放寬條件候選（僅在 Tier A 不足時啟用）。
- 取樣順序：先取 Tier A 高分，再以 Tier B 補足。

## 排序分數
- 延續 `entry_score`，但分層取樣而非單一路徑截斷。
- 目的是兼顧品質與覆蓋率（coverage）。

## 優化目標（多目標）
- `score = return_component - risk_penalty - coverage_penalty`
- `risk_penalty` 至少涵蓋：`stop_loss_ratio`、虧損交易數。
- `coverage_penalty` 透過目標區間控制 `entered_count`：
  - 過低扣分（不可交易）
  - 過高扣分（品質稀釋）

## 驗收方向
- 不回到 `entry_rule=all`。
- 停損占比維持在可控範圍。
- 成交筆數回到可接受區間。
- optimize 與 backtester 的月度方向一致性提升。
