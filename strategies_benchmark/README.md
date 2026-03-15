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
- **Label**：每月內按 `fwd_return_pct` 排名，分成 **10 個 decile**（0=最差，9=最好）
- **fwd_return_pct 定義**：月份 M 的 entry_date open 買入，M+1 entry_date **前一個交易日** open 賣出
- **Group**：每個月為一個 group
- **超參數**：`n_estimators=500, learning_rate=0.03, num_leaves=31`
- **評估指標**：Spearman IC（預測排名 vs 實際報酬排名的相關係數）
- **模型位置**：`models_selection/<cutoff_year>/<cutoff_month>/selection_model.pkl`

Walk-forward scoring 由 `backtester/run_rolling.py` 在回測時即時執行，
每個月 M 使用 cutoff < M 的最新模型，避免 look-ahead bias。

---

## Benchmark 結果與可重現性

### 基準回測結果

| 指標 | 數值 |
|------|------|
| 期間 | 2022/07 – 2025/10 |
| 閉倉交易數 | 300 |
| 勝率 | **65.3%**（196/104）|
| 平均報酬 | **7.12%** |
| Gross PnL | 2,319,597 TWD |
| Net PnL | **2,134,045 TWD** |

結果存放於 `backtester_benchmark/rolling_summary.json`。

> **舊基準**（quintile labels, n_estimators=200, num_leaves=15）：Net PnL=2,029,746，勝率=64.33%。

---

### 重現方法

```bash
# 1. 使用 benchmark 版 feature_return_analysis.csv（關鍵：直接複製，不要重新生成）
cp strategies_benchmark/output/feature_return_analysis.csv strategies/output/feature_return_analysis.csv

# 2. 刪除舊模型
rm -rf models_selection/2022 models_selection/2023 models_selection/2024 models_selection/2025

# 3. 訓練（batch_train 不呼叫 analyze_feature_returns，直接用上面複製的版本）
venv/bin/python3 strategies/batch_train_selection_model.py

# 4. 打分 + 回測 + 統計
venv/bin/python3 strategies/batch_score_and_publish.py
venv/bin/python3 backtester/run_rolling.py \
  --start_year 2022 --start_month 7 \
  --end_year 2025 --end_month 10 \
  --top-n 10 --position-amount 100000
venv/bin/python3 backtester/summarize_range.py
```

---

### 為什麼不能直接重跑 `analyze_feature_returns.py`？

`feature_return_analysis.csv` 是整個 ML pipeline 的訓練資料集，每一列為「某股票在某月的特徵值 + 實際持有報酬（fwd_return_pct）」。

重新執行 `analyze_feature_returns.py` 會讀取 `dataset_strategy.csv` 裡的特徵欄位，而其中 **`pe_percentile_official`**（PE 在全市場的歷史百分位排名）是即時對 DB 計算的，會隨著 DB 資料更新有微小浮動（平均差異約 0.08，最大約 1.06）。

雖然差異很小，但 LGBMRanker 學的是**月內排名**。微小的特徵差異就可能讓兩支股票的排名對調，導致每月選出的前 10 名不同，進而造成回測結果明顯差異：

| | Net PnL | 勝率 |
|--|---------|------|
| benchmark CSV（保存版）| **2,029,746** | 64.33% |
| 重新生成 CSV（pe_percentile 微差）| 1,838,208 | 65.3% |

其他 52 個特徵（包含 `pred_upside_pct`）在 EPS 模型未重訓的情況下完全可重現，差異僅來自 `pe_percentile_official`。

---

### 特徵實驗的教訓（2026/03）

#### 實驗一：Spearman 篩選特徵（失敗）

以 Spearman ≥ 0.02 篩選特徵（只保留 18 個正向信號特徵）並不能超越基準，反而比基準差。實驗結果：

| 版本 | Net PnL | 勝率 |
|------|---------|------|
| 舊基準（53 特徵） | **2,029,746** | **64.33%** |
| 18 特徵（Spearman ≥ 0.02） | 1,828,612 | 60.3% |
| 18 特徵 + n=300, leaves=31 | 1,789,655 | 60.3% |
| 22 特徵（Spearman ≥ 0.01） | 1,767,262 | 60.3% |

**結論**：個別特徵的 Spearman 為負不代表對模型有害。負相關特徵在 LightGBM ensemble 中可能與其他特徵產生有用的交互作用，強制移除反而讓模型失去信號。

---

#### 實驗二：增量特徵 + 超參調整（2026/03，成功超越基準）

採增量策略（不移除任何特徵），依序實驗：

| 實驗 | 變更 | Net PnL | 勝率 | 結果 |
|------|------|---------|------|------|
| 舊基準 | n_estimators=200, lr=0.05, num_leaves=15, n_bins=5 | 2,029,746 | 64.33% | — |
| A1 | 提升複雜度（500/0.03/31），quintile 不變 | 1,846,970 | 65.3% | 未超越（win_rate 提升但 PnL 下降） |
| **A2** | A1 + decile labels（n_bins=10） | **2,134,045** | **65.3%** | **成功** |
| B | A2 + 4 個新特徵（foreign_net_5d 等） | 1,781,941 | 63.0% | 未超越 |

**A1 分析**：複雜度提升後 quintile（5 級）標籤太粗，模型排名監督信號不足，導致 PnL 下降。

**A2 分析**：decile（10 級）提供更細的排名監督信號，與提高容量（num_leaves=31）的模型相輔相成，兩項指標同步改善。

**B 分析**：新增的 4 個機構流量特徵（`foreign_net_5d`, `trust_net_5d`, `smart_money_net_5d`, `hist_vol_20d`）與現有的 `foreign_held_ratio`、`trust_held_ratio`、`foreign_streak_days` 高度相關，造成特徵冗餘，加上 `trust_net_5d` 幾乎無信號（Spearman=0.01），反而引入噪音。57 個特徵在有限訓練樣本下讓 LGBMRanker 更難收斂。

**新基準 (A2)**：`n_estimators=500, learning_rate=0.03, num_leaves=31, n_bins=10`

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

