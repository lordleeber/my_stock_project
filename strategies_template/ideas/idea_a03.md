# Idea A03: 低換手高 Conviction 規則式策略（v3）

## 參考來源
- `idea_a01.md`（規則式多因子策略 v1）
- `idea_a02.md`（可交易性優先的規則式策略 v2）
- `strategies/backtester_feedback.md`（目前回測反饋與失效原因）

## 優缺點比較
- `idea_a01.md` 優點：
  - 規則簡單，可解釋性高。
  - 在弱市有一定防守能力。
- `idea_a01.md` 缺點：
  - 候選容易過少。
  - 無法兼顧不同 regime 的交易需求。

- `idea_a02.md` 優點：
  - 有 regime 分層與兩段式進場，覆蓋率較高。
  - 能把成本、coverage、停損比納入 optimize。
- `idea_a02.md` 缺點：
  - 仍容易落入「候選變多但品質不夠厚」的情況。
  - 回測顯示 2024、2025 的主要問題是成本後報酬不足，而不是沒進到場。
  - 同一框架內持續微調，邊際改善有限。

## 為何此版更好
- 不再追求更高 coverage，而是明確追求更少但更厚的單筆 edge。
- 直接把策略目標從「可交易性優先」改成「成本後 alpha 優先」。
- 與 `idea_a02.md` 最大差異：
  - 候選數量受硬上限控制。
  - entry 僅保留最有效的主訊號。
  - optimize 明確懲罰高換手與低單筆期望值。
- 預期改善：
  - 降低 `sold_count`
  - 降低 `total_cost / total_capital`
  - 提高 `gross_pnl` 留存到 `net_pnl` 的比例
- 主要 trade-off：
  - coverage 下降
  - 弱勢或盤整月份可能更常出現無交易月份

## 策略定位
- 類型：低換手、高 conviction 的規則式選股策略。
- 核心目標：減少邊際交易，讓成本不再吃掉大部分毛利。

## 設計原則
- 少做，不亂做。
- 單筆交易 edge 必須足以覆蓋成本與停損風險。
- 不再擴充特徵，先從既有特徵中挑出最有效者。

## 核心訊號（預計保留）
- 價值 / 預期空間：
  - `pred_upside_pct`
  - `eps_revision`
- 趨勢：
  - `close_vs_ma20`
  - `close_vs_ma60`
- 籌碼：
  - `foreign_net_20d_lots`
  - `inst_net_20d_lots`

## 明確刪減方向
- 不再讓太多次要因子參與決策權重。
- 不再以 coverage 為主要優化方向。
- Bull regime 不再做大幅候選擴容。

## 進場邏輯（規劃）
- 先做硬門檻：
  - `pred_upside_pct >= stronger_upside_floor`
  - `close_vs_ma60 >= stronger_trend_floor`
  - `foreign_net_20d_lots` 與 `inst_net_20d_lots` 至少一強一不弱
  - `atr20_pct <= strict_atr_cap`
- 再做排序：
  - 只用少數主因子做 `entry_score`
- 最後只保留每月固定少量標的：
  - 例如 Top `8 ~ 12`

## 出場與持有哲學（規劃）
- 不追求頻繁停利停損觸發。
- 偏向拉長持有天數，讓獲利單有延展空間。
- 停損保守保留，但停利不應過早截斷。
- 可考慮：
  - 放寬固定停利
  - 或以 `target_price_if_above_entry` / trailing stop 為主

## Optimize 方向（規劃）
- objective 優先順序改為：
  1. `net_return`
  2. `cost_rate`
  3. `profit_factor`
  4. `max_drawdown`
- 新約束應包含：
  - 年度或區間 `sold_count` 上限
  - `estimated_cost_rate` 上限
  - `profit_factor >= 1`
  - `win_rate` 下限
- coverage 不再是主要加分項，只保留最低可接受門檻

## 預期行為
- 相較 `idea_a02.md`：
  - 交易筆數顯著下降
  - 毛利可能下降，但淨利留存率應提升
  - 在趨勢年不一定全面超越 baseline，但應減少「做很多卻幾乎沒賺」的情況

## 驗證重點
- 先看：
  - `sold_count`
  - `total_cost`
  - `net_pnl / gross_pnl`
- 再看：
  - `2024` 是否能穩定維持正報酬
  - `2025` 是否能避免 `gross_pnl` 幾乎被成本吃光
