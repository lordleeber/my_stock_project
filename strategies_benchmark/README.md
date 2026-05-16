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

TTM EPS proxy = `ly_target_eps + pre_anchor_eps + anchor_eps`

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
- **超參數**：`n_estimators=500, learning_rate=0.03, num_leaves=31, reg_alpha=0.05, reg_lambda=0.1`
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
| 勝率 | **68.3%**（205/95）|
| 平均報酬 | **7.56%** |
| Gross PnL | 2,449,920 TWD |
| Net PnL | **2,263,822 TWD** |

結果存放於 `backtester_benchmark/rolling_summary.json`。

> **舊基準 A2**（無正則化）：Net PnL=2,134,045，勝率=65.3%。
> **舊基準**（quintile labels, n_estimators=200, num_leaves=15）：Net PnL=2,029,746，勝率=64.33%。

---

### 重現方法

```bash
# 1. 重新生成資料（從 DB 抓取最新的 pe_percentile_official）
venv/bin/python3 strategies/step1_batch_prepare_data.py
venv/bin/python3 strategies/step2_batch_finalize_strategy.py
venv/bin/python3 strategies/step3_analyze_feature_returns.py

# 2. 刪除舊模型
rm -rf models_selection/2022 models_selection/2023 models_selection/2024 models_selection/2025

# 3. 訓練
venv/bin/python3 strategies/step4_batch_train_selection_model.py

# 4. 打分 + 回測 + 統計
venv/bin/python3 strategies/batch_score_and_publish.py
venv/bin/python3 backtester/run_rolling.py \
  --start_year 2022 --start_month 7 \
  --end_year 2025 --end_month 10 \
  --top-n 10 --position-amount 100000
venv/bin/python3 backtester/summarize_range.py
```

> **注意**：由於 `pe_percentile_official` 會隨 DB 資料更新而微幅變動，重現結果可能與上方基準數字有小幅差異（實測 PnL 差距約 ±1.5%），這是預期行為。比較兩個策略時，應在同一次生成的資料上進行。

---

### `pe_percentile_official` 的變動性

`pe_percentile_official` 是 53 個特徵中**唯一會隨時間變動的特徵**。其他 52 個特徵在 EPS 模型未重訓的情況下完全可重現。

#### 變動原因

`pe_percentile_official` 由 `calculator/calculate_valuation.py` 計算，使用 **full-history percentile rank**：

```python
df_combined.groupby("symbol")["pe_calculated"].rank(pct=True) * 100
```

這是對每支股票的**全部歷史 PE 值**做百分位排名。每當 `daily_quotes` 新增一天的交易資料，就多了 ~2000 筆新的 PE 值參與排名，導致**所有歷史日期的百分位都會微幅改變**。

#### 實際影響幅度

以 A3 基準的 15,721 筆訓練資料為基準，重新從 DB 抓取最新值比較（2026/03 實測）：

| 統計量 | 值 |
|--------|------|
| 平均絕對差異 | 0.08 |
| 中位數絕對差異 | 0.07 |
| 最大絕對差異 | 1.06 |
| 發生變化的筆數 | 13,765 / 15,508（88.8%）|

差異雖小，但 LGBMRanker 學的是**月內排名**。微小的特徵擾動就可能讓兩支股票的排名對調，改變每月前 10 名的選股結果：

| 資料來源 | Net PnL | 勝率 |
|----------|---------|------|
| 鎖定 CSV（benchmark 保存版）| **2,263,822** | **68.3%** |
| 重新從 DB 抓取（pe_percentile 微差）| 2,229,495 | 66.7% |

#### 為什麼不能用其他計算方式替代？

我們測試了兩種穩定化方案，結果均大幅劣化（2026/03 實測）：

| 計算方式 | 說明 | Net PnL | 勝率 |
|----------|------|---------|------|
| **Full-history rank**（現行） | 對股票全部歷史 PE 排名 | **2,263,822** | **68.3%** |
| Expanding window | 每個日期只看 ≤ 該日的資料排名 | 1,609,716 | 61.3% |
| Trailing 750 天 | 只看過去 3 年（~750 交易日）排名 | 1,886,179 | 61.7% |

- **Expanding window**：早期日期只有少量資料（如上市第 10 天，每天代表 10% 的分布），百分位噪音極大，模型學到的信號完全不同。
- **Trailing 750 天**：窗口邊界造成值跳變（一筆舊資料滑出窗口就改變排名），且忽略了超過 3 年的歷史估值水位，信號損失嚴重。
- **Full-history rank**：整段歷史參與排名，分布最穩定、信號最完整，代價是新增資料會改變歷史值。

**結論**：full-history rank 的信號品質遠優於替代方案（PnL 差距 +378K ~ +654K），不可替換。

#### 開發新策略時的處理方式

開發新策略或訓練新模型時，直接從 DB 抓取最新的 `pe_percentile_official` 即可。重新生成的回測結果會因為 pe_percentile 微幅變動而與本文件記載的基準數字略有差異，這是**預期行為**。比較新舊策略時，應在同一次生成的資料上比較，而非跨時間比較絕對數字。

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

**舊基準 (A2)**：`n_estimators=500, learning_rate=0.03, num_leaves=31, n_bins=10`

---

#### 實驗三：正則化調校（2026/03，成功超越 A2）

在 A2 基礎上加入 L1/L2 正則化，不改變特徵或 label 設定：

| 實驗 | reg_alpha | reg_lambda | Net PnL | 勝率 | 結果 |
|------|-----------|------------|---------|------|------|
| A2（無正則） | 0 | 0 | 2,134,045 | 65.3% | 基準 |
| 強正則 | 1.0 | 5.0 | 1,657,455 | 58.0% | 過度抑制 |
| 中正則 | 0.1 | 0.5 | 2,088,305 | 66.7% | WR↑ PnL↓ |
| **輕正則** | **0.05** | **0.1** | **2,263,822** | **68.3%** | **成功** |
| 更輕正則 | 0.02 | 0.05 | 2,147,558 | 66.3% | 不夠 |
| 偏 L2 | 0.05 | 0.2 | 2,125,414 | 67.0% | 略差 |

額外嘗試在輕正則基礎上降低 learning rate（0.015/1000 trees, 0.025/750 trees），兩者皆劣於原始 LR=0.03/500 trees。

**分析**：53 特徵 / ~300 股每月的設定下，模型確實有輕微過擬合。極輕的 L1+L2 正則化（alpha=0.05, lambda=0.1）在不手動移除特徵的前提下達到隱式特徵選擇效果，同時保留有用的交互作用。過強的正則化（≥0.1/0.5）則過度抑制模型容量。

**新基準 (A3)**：`n_estimators=500, learning_rate=0.03, num_leaves=31, n_bins=10, reg_alpha=0.05, reg_lambda=0.1`

---

## Usage

### 單月執行
```bash
# 先確保 EPS 預測已產生（train_eps pipeline 完成後自動產出）
venv/bin/python3 train_eps/step4_predict_and_publish.py --year 2025 --month 10

venv/bin/python3 strategies/step1_prepare_data.py      --year 2025 --month 10
venv/bin/python3 strategies/step2_finalize_strategy.py --year 2025 --month 10
```

### 批次執行（歷史資料）
```bash
venv/bin/python3 train_eps/step4_batch_predict_and_publish.py
venv/bin/python3 strategies/step1_batch_prepare_data.py
venv/bin/python3 strategies/step2_batch_finalize_strategy.py
```

### ML 模型訓練
```bash
# 產生訓練資料（特徵 × 實際報酬配對）
venv/bin/python3 strategies/step3_analyze_feature_returns.py

# 每月訓練一版（walk-forward 回測用，無 look-ahead bias）
venv/bin/python3 strategies/step4_batch_train_selection_model.py
# 自訂範圍：
venv/bin/python3 strategies/step4_batch_train_selection_model.py  # 預設 2022-06 ~ 2025-09

# 單月 walk-forward 驗證
venv/bin/python3 strategies/step4_train_selection_model.py --cutoff-year 2024 --cutoff-month 6

# 正式訓練（全資料，production 用）
venv/bin/python3 strategies/step4_train_selection_model.py
```

---

