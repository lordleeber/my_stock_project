# Idea 02: 可交易性優先的規則式多因子策略（v2）

## 策略定位
- 類型：規則式選股 + 參數優化（承接 `idea_01`，強化可交易性）。
- 核心目標：在維持風險護欄下，提升候選覆蓋率與跨月份穩定性。
- 主要修正方向：
  - 降低「條件過硬導致成交不足」問題。
  - 以 market regime（多頭/空頭/震盪）切換門檻，避免單一參數吃全市場。

## 可用特徵（以 `common/schemas.py` 為準）
- 估值與基本面（`valuation_daily`）：
  - `ttm_eps_official`, `ttm_eps_forward`
  - `pe_official`, `pe_forward`
  - `pe_percentile_official`, `pe_percentile_forward`
  - `upside_pct`, `roe_official`, `roe_forward`
- 價量（`daily_quotes`）：
  - `open`, `high`, `low`, `close`, `volume`, `transactions`, `change`
- 籌碼（`institutional_investors`）：
  - `foreign_net`, `trust_net`, `dealer_net`, `total_net`
- 外資持股（`foreign_holding`）：
  - `foreign_held_ratio`, `foreign_investable_ratio`
- 融資券與放空壓力（`margin_pressure_analysis` + `short_interest_analysis`）：
  - `margin_usage_ratio`, `short_usage_ratio`
  - `short_cover_pressure`, `margin_pressure_score`, `short_pressure_score`
  - `sbl_balance_wow_pct`, `margin_short_balance_wow_pct`
- 股權集中度（`shareholding_concentration`）：
  - `large_holder_ratio`, `small_holder_ratio`, `concentration_spread`
  - `large_holder_ratio_wow`, `concentration_spread_wow`
- 營收與季報（`monthly_revenue` + `quarterly_reports`）：
  - `mom_pct`, `yoy_pct`, `cumulative_yoy_pct`
  - `eps_acc_yoy`, `net_income_acc_yoy`, `op_income_acc_yoy`
  - `current_ratio`, `quick_ratio`, `equity_to_assets_ratio`
- 大盤環境（`market_indices`）：
  - `index_close`, `index_change_points`

## 因子設計（僅用當下可得資訊）
- 預估成長與估值：
  - `eps_revision = ttm_eps_forward / ttm_eps_official - 1`
  - `valuation_room = upside_pct`
  - `pe_safe = 1 - pe_percentile_forward`（分位越低越有安全邊際）
- 籌碼動能：
  - `foreign_net_20d_lots = rolling_sum20(foreign_net) / 1000`
  - `inst_net_20d_lots = rolling_sum20(trust_net + dealer_net) / 1000`
- 放空/槓桿壓力：
  - `short_pressure_score`、`margin_pressure_score` 作為風險扣分項
- 交易結構：
  - `turnover_proxy = volume / issued_shares`
  - `liquidity_score` 由 `volume`、`transactions` 標準化後組成
- 趨勢與波動（由 `daily_quotes` 衍生）：
  - `close_vs_ma20`, `close_vs_ma60`
  - `atr20_pct = atr20 / close * 100`

## Market Regime（門檻分層）
- 以大盤 `index_close` 判定：
  - Bull：`ma20(index_close) > ma60(index_close)`
  - Bear：`ma20(index_close) < ma60(index_close)` 且 `index_close < ma20`
  - Sideways：其餘情況
- 各 regime 參數分開優化：
  - Bull：放寬進場，追求 coverage 與報酬延展。
  - Bear：收緊風險，降低 `atr20_pct` 上限與停損容忍。
  - Sideways：偏重籌碼與估值保守條件。

## 進場規則（兩段式）
- Stage A: 核心硬過濾
  - `volume >= min_volume`
  - `eps_revision >= eps_revision_min`
  - `close_vs_ma60 >= trend_floor`
  - `atr20_pct <= atr_cap`
  - 關鍵欄位缺值則不進場
- Stage B: Tier 補量（可交易性保底）
  - 若 Stage A 候選 `< min_candidates`，啟用 Tier B 放寬：
    - `eps_revision_min` 下修
    - `trend_floor` 下修（允許接近 MA60）
    - 籌碼由「雙正」放寬為「外資或法人其一為正」
  - 仍保留絕對風險底線：`atr20_pct <= hard_atr_cap`

## 排序分數（軟排序）
- `entry_score = value_score + chip_score + trend_score + quality_score - risk_penalty`
- 建議子分數：
  - `value_score`: `z(upside_pct) + z(eps_revision) + z(pe_safe)`
  - `chip_score`: `z(foreign_net_20d_lots) + z(inst_net_20d_lots)`
  - `trend_score`: `z(close_vs_ma20) + z(close_vs_ma60)`
  - `quality_score`: `z(roe_forward) + z(eps_acc_yoy) + z(op_income_acc_yoy)`
  - `risk_penalty`: `z(atr20_pct) + z(short_pressure_score) + z(margin_pressure_score)`
- 出場股票池：
  - 優先取 Top N。
  - 若不足，擴充至 Top %（上限受 regime 控制）。

## 出場與風控
- 停利/停損採參數網格：
  - `take_profit_ratio`: 6% ~ 12%
  - `stop_loss_ratio`: 3% ~ 7%
  - `max_hold_days`: 10 ~ 30
- 同日同時觸發停利與停損：採保守優先（先停損）。
- 風險限制：
  - 單檔預算制（與 backtester 同口徑）
  - `stop_loss_ratio` 上限約束
  - 高回撤懲罰與月份虧損集中懲罰

## 優化目標（v2 重點）
- 主要目標：在風險可控下提升穩定超越 baseline 機率。
- 建議目標函數（示意）：
  - `objective = annual_return - a*max_drawdown - b*stop_loss_ratio - c*turnover_cost + d*coverage_score`
- 必要約束：
  - 最小成交筆數
  - 最低月份覆蓋率（避免只在少數月份交易）
  - regime 分層後，各層不得出現極端失衡（例如僅 Bull 有交易）

## 預期行為
- 相較 `idea_01`：
  - 交易覆蓋率提升，降低「無法進場」月份。
  - 在 Bear/震盪市的回撤控制更穩定。
  - 整體績效對單一門檻敏感度下降，跨年度穩定性更好。
