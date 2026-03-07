# Idea 02: 可交易性優先的規則式多因子策略（v2）

## 策略定位
- 類型：規則式選股 + 參數優化（承接 `idea_01`，以可交易性與成本後報酬為主）。
- 核心目標：
  - 避免 `idea_01` 因條件過硬導致候選過少。
  - 透過 regime 分層提高不同市況下的適應性。
  - 優化目標從單純報酬擴充到 coverage、成本、停損比與交易效率。

## 目前實作用到的資料與特徵
- 估值與 EPS：
  - `ttm_eps_official`
  - `pred_lgb_delta`
  - `ttm_eps_forward_live`
  - `predict_target_price_live`
  - `pred_upside_pct`
- 價量與技術：
  - `q3_close`, `volume_lots`
  - `ma20`, `ma60`
  - `close_vs_ma20`, `close_vs_ma60`
  - `atr20_pct`
- 籌碼與風險：
  - `foreign_net_20d_lots`
  - `inst_net_20d_lots`
  - `margin_pressure_score`
  - `short_pressure_score`
- 品質與估值補充：
  - `roe_forward`
  - `eps_acc_yoy`
  - `op_income_acc_yoy`
  - `pe_percentile_forward`

## 衍生因子（目前 code 版本）
- `eps_revision = ttm_eps_forward_live / ttm_eps_official_live - 1`
- `pe_safe = 1 - pe_percentile_forward`
- `foreign_net_20d_lots = rolling_sum20(foreign_net) / 1000`
- `inst_net_20d_lots = rolling_sum20(trust_net + dealer_net) / 1000`
- `pred_upside_pct = (predict_target_price_live - q3_close) / q3_close * 100`
- `close_vs_ma20 = close / ma20 - 1`
- `close_vs_ma60 = close / ma60 - 1`
- `atr20_pct = atr20 / close * 100`

## Market Regime（目前判定方式）
- Bull：`ma20(index_close) > ma60(index_close)`
- Bear：`ma20(index_close) < ma60(index_close)` 且 `index_close < ma20`
- Sideways：其餘情況

目前 regime 參數：
- Bull：
  - `eps_min = -0.03`
  - `trend_floor = -0.02`
  - `atr_cap = 7.0`
- Bear：
  - `eps_min = 0.02`
  - `trend_floor = 0.01`
  - `atr_cap = 5.0`
- Sideways：
  - `eps_min = 0.0`
  - `trend_floor = 0.0`
  - `atr_cap = 6.0`

## 進場規則（兩段式，對齊目前 code）
- Stage A：核心硬過濾
  - `volume_lots >= min_volume_lots`
  - Bull 時成交量門檻可放寬為 `max(100, min_volume_lots * bull_min_volume_mult)`
  - `eps_revision >= eps_min`
  - `close_vs_ma60 >= trend_floor`
  - `atr20_pct <= atr_cap`
  - `pred_upside_pct >= min_upside_pct`
  - 關鍵欄位缺值則不進場
- Stage A 籌碼條件
  - Bull：
    - 外資或法人其一為正
    - 另一方不可明顯為負（目前用 `>= 0`）
  - Bear / Sideways：
    - `foreign_net_20d_lots > 0`
    - `inst_net_20d_lots > 0`
- Stage B：候選不足時的補量
  - 啟動條件：Stage A 候選 `< min_candidates`
  - 放寬內容：
    - `eps_revision` 下修 `tierb_eps_relax`
    - `trend_floor` 下修 `tierb_trend_relax`
    - `pred_upside_pct` 下限降為 `max(1.5, min_upside_pct - 1.0)`
    - `atr20_pct <= hard_atr20_pct`
  - Bull 的 Stage B 額外放寬：
    - 成交量可再放寬
    - 籌碼由「一強一不弱」放寬為「一強、另一側不低於 -2 lots」

## 排序分數（目前 code）
- 子分數：
  - `value_score = z(pred_upside_pct) + z(eps_revision) + z(pe_safe)`
  - `chip_score = z(foreign_net_20d_lots) + z(inst_net_20d_lots)`
  - `trend_score = z(close_vs_ma20) + z(close_vs_ma60)`
  - `quality_score = z(roe_forward) + z(eps_acc_yoy) + z(op_income_acc_yoy)`
  - `risk_penalty = z(atr20_pct) + z(short_pressure_score) + z(margin_pressure_score)`
- `entry_score`
  - Bull：
    - `1.2*value + 1.0*chip + 1.35*trend + 0.9*quality - 0.75*risk`
  - Bear：
    - `1.0*value + 1.05*chip + 0.8*trend + 1.0*quality - 1.2*risk`
  - Sideways：
    - `value + chip + trend + quality - risk`

## 候選保留策略（目前 code）
- 先按 `entry_score` 由高到低排序。
- 預設 `top_n = 30`。
- 若不足 `min_candidates`，再用 `top_entry_score_pct` 擴充。
- Bull 會做有限度擴容，但已收斂為保守版：
  - `bull_topn_mult = 1.25`
  - `bull_min_volume_mult = 0.85`
  - Bull 最低 `top_pct` 提升到 `0.45`

## 出場與參數空間（目前 optimize）
- `entry_rule`
  - `target_above_entry_ratio`
  - `pullback_from_ref_close`
- `take_profit_rule`
  - `fixed_pct`
  - `target_price_if_above_entry`
- `exit_rule`
  - `stop_loss_pct = 3% ~ 8%`
  - `max_hold_days = 15 / 20 / 25 / 30`
  - 部分 trial 允許 `trailing_stop_pct`
- 同日同時觸發停利與停損：採保守優先（先停損）

## 部位口徑
- 與 backtester 對齊：每檔預算制
- 目前固定：
  - `max_position_amount = 100000`
  - 非固定 `1000` 股策略假設

## 優化目標（目前 code）
- 主要目標不是最大化毛報酬，而是提高成本後可用性。
- 約束：
  - `min_entered_count`
  - `min_month_coverage`
  - `max_stop_loss_ratio`
  - `min_profit_factor`
  - `min_win_rate`
- 追蹤指標：
  - `coverage_score`
  - `up_month_score`
  - `max_drawdown_pct`
  - `turnover_ratio`
  - `profit_factor`
  - `win_rate`
  - `estimated_cost_rate`
- 目前 objective（概念）：
  - `return`
  - 減去 `drawdown`、`stop_loss_ratio`、`turnover`、`estimated_cost_rate`
  - 加上 `coverage_score`、`up_month_score`

## 目前版本的實務結論
- 相較 `idea_01`，`idea_02` 的確提升了 coverage 與 regime 彈性。
- 但實際回測顯示：
  - 若 Bull 放寬過頭，會快速惡化成本後報酬。
  - 問題核心不是缺特徵，而是交易品質與成本控制不足。
- 因此目前 code 已收斂到「減法版 idea_02」：
  - 不再增加新特徵
  - 強調 `min_upside_pct`
  - 強調 `profit_factor`、`win_rate`、`cost_rate` 約束
  - 目標是壓低低品質交易，而不是單純擴大 coverage
