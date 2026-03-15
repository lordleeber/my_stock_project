# Strategies

ML-based stock selection pipeline. Filters a universe of ~300 stocks using hard criteria,
then trains a LightGBM Ranker to select the top candidates each month.

---

## Pipeline Overview

```
train_eps/predict_and_publish.py   EPS 預測 → models_eps/<year>/<month>/predictions_results.csv
                                                               ↓
prepare_data.py          硬篩選 → dataset_strategy.csv
      ↓
finalize_strategy.py     merge 預測 + entry_date + 技術面特徵 → dataset_strategy.csv (final)
                                                               → trade_candidates.csv
```

```
analyze_feature_returns.py   特徵 × 實際報酬配對 → feature_return_analysis.csv  ← 離線，定期重跑
      ↓
train_selection_model.py     訓練 LGBMRanker → models_selection/<cutoff>/selection_model.pkl
```

---

## Hard Filters（prepare_data.py）

| 條件 | 值 |
|------|----|
| TTM EPS proxy | > 2.0 |
| 日均成交量 | > 500 張 |

TTM EPS proxy = `ly_target_eps + prev_eps + anchor_eps`

---

## Output Files

### strategies/output/<year>/<month>/

| 檔案 | 產生自 | 說明 |
|------|--------|------|
| `dataset_strategy.csv` | prepare_data → finalize_strategy | 完整特徵快照（基本面 + 籌碼面 + 技術面） |
| `trade_candidates.csv` | finalize_strategy | 候選股清單（含 entry_date、pred_upside_pct） |

### models_eps/<year>/<month>/

| 檔案 | 產生自 | 說明 |
|------|--------|------|
| `predictions_results.csv` | train_eps/predict_and_publish | EPS 預測結果（含 pred_lgb_delta），由 finalize_strategy 讀取 |

---

## dataset_strategy.csv 欄位

### 基本面
`symbol`, `name`, `industry`, `ttm_eps`, `pe_current`, `volume_lots`, `close`,
`anchor_eps`, `predict_target_eps`, `pred_upside_pct`, `predict_target_price`, `entry_date`

### 籌碼面
| 欄位 | 說明 |
|------|------|
| `foreign_held_ratio` | 外資持股比例 |
| `trust_held_ratio` | 投信持股比例 |
| `large_holder_ratio` | 大戶持股比例（TDCC level 12–15，> 4,000 張） |
| `large_holder_ratio_wow` | 大戶持股週變化 |
| `large_holder_two_week_up` | 連兩週大戶持股上升（0/1） |
| `mid_holder_ratio` | 中實戶持股比例（TDCC level 9–11，400–4,000 張） |
| `mid_holder_ratio_wow` | 中實戶持股週變化 |
| `small_holder_ratio` | 散戶持股比例（TDCC level 1–8，1–400 張） |
| `small_holder_ratio_wow` | 散戶持股週變化 |
| `concentration_spread` | 大戶比例 - 散戶比例 |
| `concentration_spread_wow` | concentration_spread 週變化 |
| `dealer_held_ratio` | 自營商持股比例 |

### 估值面（由 valuation_daily 查詢）
| 欄位 | 說明 |
|------|------|
| `roe_official` | ROE（TTM，使用已公布財報） |
| `pe_percentile_official` | 目前 PE 在歷史中的百分位 |

### 市場情緒（由 margin_pressure_analysis / short_interest_analysis 查詢）
| 欄位 | 說明 |
|------|------|
| `margin_usage_ratio` | 融資使用率（餘額/限額） |
| `short_cover_pressure` | 軋空壓力指標 |
| `sbl_sell_repay_ratio` | 借券賣出／還券比 |

### 基本面品質（由 quarterly_reports 查詢，anchor_q PIT 對齊）
| 欄位 | 說明 |
|------|------|
| `anchor_debt_ratio` | 負債比（total_liabilities / total_assets） |
| `pb_ratio` | 股價淨值比（q3_close / nav_per_share） |
| `current_ratio` | 流動比率 |
| `eps_acc_yoy` | 累計 EPS YoY 成長率 |
| `revenue_acc_yoy` | 累計營收 YoY 成長率 |

### 技術面（由 feature_engineering.py 從 technical_indicators 表查詢）
`close_vs_ma5/10/20/60/240`, `vol_vs_vma5/10/20`, `ma5_vs_ma20`, `ma20_vs_ma60`,
`k`, `d`, `rsi6`, `rsi12`, `macd_dif`, `macd_dea`, `macd_hist`, `bb_position`,
`foreign_streak_days`, `trust_streak_days`, `dealer_streak_days`

### 月營收動能（由 feature_engineering.py 從 monthly_revenue 表查詢，PIT-safe）
| 欄位 | 說明 |
|------|------|
| `revenue_yoy_1m` | 最新月營收 YoY % |
| `revenue_mom_1m` | 最新月營收 MoM % |
| `revenue_cum_yoy` | 當年累計營收 YoY % |
| `revenue_yoy_3m_avg` | 近 3 個月 YoY % 平均 |
| `revenue_yoy_accel` | YoY 加速度（最新月 YoY - 3 個月前 YoY） |
| `revenue_positive_streak` | 連續 YoY > 0 的月數 |

PIT 保證：以 `publish_time <= entry_date` 過濾，entry_date 約為月份 M/11，可取得 M/10 前公布的 M-1 月營收。

---

## ML Model

- **演算法**：LightGBM Ranker（`objective="lambdarank"`）
- **特徵數**：53 個（基本面 + 籌碼面 + 估值面 + 市場情緒 + 基本面品質 + 技術面 + 月營收動能）
- **Label**：每月內按 `fwd_return_pct` 排名，分成 5 個 quintile（0=最差，4=最好）
- **fwd_return_pct 定義**：月份 M 的 entry_date open 買入，M+1 entry_date **前一個交易日** open 賣出
- **Group**：每個月為一個 group
- **評估指標**：Spearman IC（預測排名 vs 實際報酬排名的相關係數）
- **模型位置**：`models_selection/<cutoff_year>/<cutoff_month>/selection_model.pkl`

Walk-forward scoring 由 `backtester/run_rolling.py` 在回測時即時執行，
每個月 M 使用 cutoff < M 的最新模型，避免 look-ahead bias。

---

## Usage

### 單月執行
```bash
# 先確保 EPS 預測已產生（train_eps pipeline 完成後自動產出）
venv/bin/python3 train_eps/predict_and_publish.py --year 2025 --month 10

venv/bin/python3 strategies/prepare_data.py      --year 2025 --month 10
venv/bin/python3 strategies/finalize_strategy.py --year 2025 --month 10
```

### 批次執行（歷史資料）
```bash
venv/bin/python3 train_eps/batch_predict_and_publish.py
venv/bin/python3 strategies/batch_prepare_data.py
venv/bin/python3 strategies/batch_finalize_strategy.py
```

### ML 模型訓練
```bash
# 產生訓練資料（特徵 × 實際報酬配對）
venv/bin/python3 strategies/analyze_feature_returns.py

# 每月訓練一版（walk-forward 回測用，無 look-ahead bias）
venv/bin/python3 strategies/batch_train_selection_model.py
# 自訂範圍：
venv/bin/python3 strategies/batch_train_selection_model.py  # 預設 2022-06 ~ 2025-09

# 單月 walk-forward 驗證
venv/bin/python3 strategies/train_selection_model.py --cutoff-year 2024 --cutoff-month 6

# 正式訓練（全資料，production 用）
venv/bin/python3 strategies/train_selection_model.py
```

---

