# Strategies Strategy Blueprint

## 採用策略版本
- 策略邏輯來源：`strategies_template/ideas/idea_01.md`
- 本文件用途：定義 `strategies/` 目前實作規格（路徑、流程、風控、優化口徑）

## 策略定位（Idea 01）
- 類型：規則式選股 + 參數優化
- 目標：避免無差別進場，降低停損占比，維持可解釋性

## 核心訊號（Idea 01）
- EPS 預估相對優勢：`ttm_eps_forward_live` 相對 `ttm_eps_official_live`
- 籌碼動能：
  - `foreign_net_20d_lots = rolling_sum20(foreign_net) / 1000`
  - `inst_net_20d_lots = rolling_sum20(trust_net + dealer_net) / 1000`
- 技術位置：`close_vs_ma60 = close / ma60 - 1`
- 波動風險：`atr20_pct = atr20 / close * 100`
- 流動性：`volume_lots`

## 進場硬過濾（Idea 01）
- `volume_lots >= 200`
- `ttm_eps_forward_live >= ttm_eps_official_live`
- `close > ma60`
- `foreign_net_20d_lots > 0`
- `inst_net_20d_lots > 0`
- `atr20_pct <= atr_threshold`
- 任一關鍵因子缺值則不進場

## 排序與風控（Idea 01）
- `entry_score = pred_upside_z + chip_score + tech_score - vol_penalty`
- 保留高分區間（Top N 或 Top %）
- 禁用 `entry_rule=all`
- 優化需同時考慮報酬與風險約束：
  - 最小成交筆數
  - `stop_loss_ratio` 上限
  - 高回撤懲罰

## 月份與日期規則
- release date：`05/08/11 -> 15`，其餘月份 `-> 10`
- `entry_date`：release 次日（若休市順延下一交易日）

## 檔案路徑規格（Production）
- candidates（build_candidates）：
  - `strategies/output/<year>/<month>/results_candidates/trade_candidates_<release_yyyymmdd>.csv`
- quotes cache（cache_daily_quotes）：
  - 寫回各 period 自己目錄
  - `strategies/output/<period_year>/<period_month>/results_quotes_cache/daily_quotes_*.csv`
  - 若目的檔已存在，視為 cache 完成，直接 skip
- optimize output（optimize_strategy）：
  - `strategies/output/<year>/<month>/results_optimize/optimization_results_all.csv`
  - `strategies/output/<year>/<month>/results_optimize/optimization_results_top20.csv`
  - `strategies/output/<year>/<month>/results_optimize/best_strategy.json`
  - `strategies/output/<year>/<month>/results_optimize/optimization_summary.json`

## Pipeline
1. `prepare_data.py`
2. `predict_published.py`
3. `build_candidates.py`
4. `cache_daily_quotes.py`
5. `optimize_strategy.py`

## Fail-fast 規則
- candidates 檔缺失：`FileNotFoundError`
- quotes cache 缺失：`FileNotFoundError`
- candidates 存在但 symbol 為空（cache 階段）：`RuntimeError`
- 不做舊路徑 fallback

## 保底規則
- `build_candidates.py` 若篩選後為 0 檔：強制加入 `2330`
- 若 `2330` 也不存在：直接報錯

## 目標價公式
- `predict_target_price = pe_current * ttm_eps_forward_live`
- 不再使用 `pe_current * predict_target_eps`

## Optimize 規則（已定案）
- 只使用 historical A / B：
  - A：去年同月
  - B：上月
- 不做當月套用回測（不產生 `current_month_backtest.csv`）
- as-of cutoff：使用本次執行月份的 release date
  - 例：`--year 2023 --month 08` -> cutoff `2023-08-15`
- 同一 cutoff 同時套用到 historical A / B，避免未來資料滲漏

## 最低交付檔案
1. `results_candidates/trade_candidates_<release_yyyymmdd>.csv`
2. `results_optimize/best_strategy.json`
