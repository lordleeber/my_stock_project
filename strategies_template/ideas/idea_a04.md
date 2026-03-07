# Idea A04: 成本受控且保留上行捕捉的高 Conviction 策略（v4）

## 參考來源
- `idea_a02.md`（可交易性優先的規則式策略 v2）
- `idea_a03.md`（低換手高 conviction 規則式策略 v3）
- `strategies/strategy_blueprint.md` 的最新 backtester 回寫（2022/08 ~ 2025/10）

## 優缺點比較
- `idea_a02.md` 優點：
  - 候選覆蓋較高，較不容易完全沒交易。
  - 在強勢或輪動較快的月份，較容易捕捉到行情。
- `idea_a02.md` 缺點：
  - 候選較鬆，容易產生太多邊際交易。
  - 成本拖累明顯，容易出現毛利被費用吃掉的問題。

- `idea_a03.md` 優點：
  - 明確限制候選數量與高換手。
  - `2023` 顯著優於 baseline，證明高 conviction 框架有效。
  - 方向正確地把重點放在成本後報酬，而不是單純 coverage。
- `idea_a03.md` 缺點：
  - `2024` 的 `gross_pnl` 幾乎被 `total_cost` 吃光，表示單筆 edge 還不夠厚。
  - `2025` 雖然正報酬，但明顯落後 baseline，代表強勢年收益捕捉不足。
  - 過度收斂候選與進場條件，可能錯過高趨勢但波動較大的強勢股。

## 為何此版更好
- `a04` 不回到高 coverage 路線，但也不再單純把交易數壓到更低。
- 核心改進是：
  - 針對弱 edge 交易更嚴格。
  - 對高趨勢、高上修、高籌碼共振的標的保留彈性，不因波動稍高就直接排除。
- 預期改善：
  - `2024` 降低成本吃光毛利的情況。
  - `2025` 提升對強勢股與趨勢年的收益捕捉。
  - 保留 `2023` 已證明有效的高 conviction 優勢。
- 主要 trade-off：
  - 邏輯會比 `a03` 稍複雜，需接受部分 regime 下門檻不完全一致。
  - 候選數量可能略高於 `a03`，但不能回到 `a02` 那種廣撒網。

## 策略定位
- 類型：成本受控、但保留上行捕捉能力的高 conviction 規則式策略。
- 核心目標：
  - 避免 `2024` 類型的成本拖累。
  - 避免 `2025` 類型的強勢年明顯落後 baseline。

## 設計原則
- 少做，但不能錯過最強的那批股票。
- 優先排除低單筆期望值交易，而不是一味追求更低交易數。
- 硬門檻與排序邏輯要區分：
  - 弱 edge 標的直接排除。
  - 強趨勢高品質標的允許適度放寬次要風險條件。

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
- 風險：
  - `atr20_pct`

## 相較 a03 的主要調整方向
- 不再用單一固定硬門檻處理所有標的。
- 改成兩層候選：
  - Core bucket：
    - 維持高 conviction、低波動、強上修的嚴格條件。
  - Momentum bucket：
    - 若 `pred_upside_pct`、`close_vs_ma60`、籌碼三者同時很強，允許 `atr20_pct` 稍微放寬。
- 候選上限仍保留，但不再完全固定死 Top `8 ~ 12`：
  - 預設核心數量較小。
  - 只有在高品質強勢訊號明顯時，才允許擴到較高上限。

## 進場邏輯（規劃）
- 先做共同底線：
  - `pred_upside_pct >= base_upside_floor`
  - `eps_revision >= base_revision_floor`
  - `close_vs_ma60 >= base_trend_floor`
- 再分 bucket：
  - Core bucket：
    - `atr20_pct <= strict_atr_cap`
    - `foreign_net_20d_lots` / `inst_net_20d_lots` 至少一強一不弱
  - Momentum bucket：
    - `pred_upside_pct` 顯著高於 base floor
    - `close_vs_ma20`、`close_vs_ma60` 顯著偏強
    - 允許 `atr20_pct` 高於 core bucket，但不可過高
- 最後做總排序：
  - Core 與 Momentum 一起排序，但 Core 權重可稍高，避免策略完全漂向追價

## 候選排序（規劃）
- `entry_score` 預計拆成：
  - `upside_score`
  - `revision_score`
  - `trend_score`
  - `chip_score`
  - `risk_penalty`
- 與 `a03` 差異：
  - 提高 `trend_score` 對高品質強勢股的影響
  - `risk_penalty` 不再對所有高波動標的一視同仁
  - 對 Momentum bucket 採「允許存在，但總數受控」的方式，而非直接排除

## 出場與持有哲學（規劃）
- 不追求頻繁交易。
- 相比 `a03`，對強勢股可容忍稍長持有時間。
- 停損維持保守，但停利不應過早截斷。
- 可優先考慮：
  - `target_price_if_above_entry`
  - 較寬鬆的固定停利
  - 或對強趨勢配置 trailing stop

## Optimize 方向（規劃）
- objective 優先順序維持：
  1. `net_return`
  2. `cost_rate`
  3. `profit_factor`
  4. `max_drawdown`
- 但評估重點要明確改成：
  - 不只防 cost drag
  - 也要避免強勢年大幅落後 baseline
- 新約束或診斷重點應包含：
  - `sold_count` 上限
  - `estimated_cost_rate` 上限
  - `avg_pnl_per_trade` 下限
  - `profit_factor >= 1`
  - `win_rate` 下限
- 若某組參數能大幅改善 `2024`，但讓 `2025` 明顯更差，不應視為最佳方案

## 預期行為
- 相較 `idea_a03.md`：
  - `2024` 的 `net_pnl / gross_pnl` 應改善
  - `2025` 的報酬捕捉應提升
  - `sold_count` 不應明顯回升到 `a02` 那種過高水位
- 相較 `idea_a02.md`：
  - 交易數仍應較少
  - 成本拖累應較低
  - 但不該因過度保守而在強勢年嚴重少賺

## 驗證重點
- 先看：
  - `sold_count`
  - `total_cost`
  - `net_pnl / gross_pnl`
  - `avg_pnl_per_trade`
- 再看：
  - `2024` 是否不再接近「毛利被成本吃光」
  - `2025` 是否縮小與 baseline 的差距
  - `2023` 的優勢是否仍大致保留
