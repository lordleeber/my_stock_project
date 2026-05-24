# Selection Model Experiments

2026-05-24 跑了一輪 selection model feature engineering 跟 label rewrite
探索。main 停在 P1 baseline，所有後續方向 parked 在獨立 branch。本檔記錄
方向、結果、決策依據，方便未來重拾。

## Main Timeline

| Commit | Branch | 內容 |
|---|---|---|
| d15675d | main | pre-P1 baseline (split pred_upside_pct into base/ml/total triple) |
| ebb3d15 | main | **P1: drop low-gain features** large_holder_two_week_up + revenue_positive_streak |
| 1d45f76 | main | docs: refresh column counts after P1 |

P1 是唯一 merge 到 main 的實驗。P2 (anchor_ocf_ratio) 跑了但結果 flat，已
rollback。P3 之後一律 parked 在 branch。

## Result Matrix

九指標完整對比（4Y backtest 2022-07-11 → 2026-05-16，top-10 picks，
$100K per position）。

| Phase / Branch | 4Y PnL | Win% | Trade mean | Trade median | Sharpe trade | Sharpe mo ann | Monthly std | Worst month | Best month |
|---|---|---|---|---|---|---|---|---|---|
| Pre-P1 (d15675d) | 3.82M | 65.65% | 8.32% | 5.69% | 0.443 | 2.57 | 10.97% | -24.63% | 34.53% |
| **P1 (ebb3d15, main)** | **3.96M** | **66.96%** | 8.62% | 5.69% | 0.461 | 2.91 | 10.04% | -21.60% | 34.78% |
| p3-vol-features | 4.09M | 66.52% | 8.90% | 5.43% | 0.403 | 2.77 | 11.32% | -19.36% | 36.41% |
| p5-industry-rank | 4.09M | 65.00% | 8.91% | 5.97% | 0.451 | 2.72 | 11.12% | -22.39% | 34.30% |
| p-label-sharpe | 2.48M | 60.43% | 5.40% | 1.83% | 0.292 | 2.13 | 8.59% | -9.87% | 43.90% |
| **p-label-mixed α=0.7** | 3.57M | 63.48% | 7.77% | 5.11% | 0.413 | **3.02** | 8.72% | -19.84% | 29.09% |
| p-label-mdd λ=0.5 | 3.40M | 64.78% | 7.41% | 4.41% | 0.419 | 2.75 | 9.14% | -18.89% | 33.51% |

P3 / P5 monthly std + best month 沒當下記錄到三位精度，這裡是從備份檔
（`logs/p*_baseline/rolling_*.csv`）即時重算的近似值。

## Decision Rule

「**穩定優先於絕對 PnL**」— Sharpe（per-trade 或 monthly annualized 任一）
退步幅度 > 0.05 即視為 fail，即使 PnL 改善 +3-5%。todo 原訂「三指標至少
兩個改善」太寬，實務不夠嚴。

## Findings

**P3 / P5 同 pattern（加 feature 在 P1 之上）**：

加 vol features (P3) 或 industry rank (P5) 都讓 PnL +3%，但 monthly Sharpe
退 -0.15 ~ -0.19、worst month 持平或惡化。Model 把 eps_growth_total_pct
gain（P1: 1335）大幅重分配（P3: 712, P5: 511）→ picks 變激進 → mean ↑
std ↑↑。**在 fwd_return_pct label 下，P1 feature set 已飽和**。

**Label 改寫是唯一打破 pattern 的方向**：

- Pure Sharpe label 過度修正：PnL -37%、worst month 砍半但 model 太保守。
- MDD-adjusted label λ=0.5：PnL -14%、Sharpe 仍退步。Penalty 兩面不到位。
- **Mixed label α×fwd_rank + (1-α)×sharpe_rank**：唯一改善 monthly Sharpe
  的 label 變體。

**Alpha sweep (0.60 → 0.85, step 0.05)**：

| α | PnL Δ | Sharpe_mo Δ | Worst Δ |
|---|---|---|---|
| 0.60 | -698K | -0.28 | +0.05 |
| 0.65 | -578K | +0.03 ≈ | -0.17 |
| **0.70** | **-390K** | **+0.11** ✓ | **+1.76** ✓ |
| 0.75 | -805K | -0.36 ❌ | -1.41 |
| 0.80 | -263K | -0.24 | -0.14 |
| 0.85 | -155K | -0.05 邊緣 | -0.44 |

α=0.70 是唯一 net 改善 monthly Sharpe + worst month 同時的點，且 0.65 ~
0.85 鄰居都不如它。α=0.75 outlier 顯示 label→model 關係 noisy，multi-seed
ensemble 是合理的下一步（未做）。

## How to Resume

```bash
# 看實驗 baseline 狀態
ls logs/p1_baseline/           # pre-P1 (d15675d) backtest 完整 snapshot
ls logs/p_label_baseline/      # P1 (= ebb3d15) snapshot at label experiment start
ls logs/p3_baseline/           # 同上，每個 phase 各備份一份
ls logs/tune_a60/ tune_a70/ ... # alpha sweep 各 alpha 結果

# 重拾某個 phase
git checkout p-label-mixed              # α=0.7 winner
git checkout p-label-mixed-tuning       # 6-alpha sweep code
git checkout p3-vol-features            # vol_20d/60d
git checkout p5-industry-rank           # industry rank ×3
git checkout p-label-sharpe             # pure Sharpe label
git checkout p-label-mdd                # MDD-adjusted

# 比對 scripts（untracked，沒進 main git）
ls scripts/compare_p1_*.py
```

## Post-P1 Audits — Portfolio Construction

2026-05-24 在 P1 (main) 之上做了一輪「不動 model、只調 portfolio construction」
的研究，看能不能再榨。結論：**現有 top_n=10 框架基本飽和，不要部署 regime
gate**。流程腳本見 `scripts/sweep_top_n.py` / `ml_score_distribution.py` /
`regime_diagnostic.py` / `walk_forward_gate.py`，artifact 在
`backtester/output/sweep_top_n/` 與 `scripts/output/`。

### top_n sweep (1 → 20, 4Y 同範圍)

| top_n | Sharpe_mo ann | Total PnL | Positive months | Worst month | Max DD |
|---|---|---|---|---|---|
| 1 | 2.130 | 619K | 68.1% | -26.4% | -45K |
| 5 | 2.597 | 2.18M | 80.9% | -23.9% | -162K |
| 7 | 2.980 | 3.10M | 83.0% | -21.2% | -189K |
| **9** | **2.986** | 3.70M | 83.0% | -20.8% | -205K |
| 10 (prod) | 2.910 | 3.96M | 83.0% | -21.6% | -228K |
| 11 | 2.890 | 4.39M | **87.2%** | -21.7% | -239K |
| 15 | 2.809 | 5.39M | 80.9% | -20.4% | -339K |
| 20 | 2.753 | **6.80M** | 83.0% | -21.5% | -482K |

**Sharpe 高原在 top_n = 7–11**，9 最高（2.986）、11 月度穩定度最高（87.2%）。
n=1 因高度集中 Sharpe 最差；n>11 後 mean ↓ 但 std 沒等比下降。top_n=10 跟
top_n=9 的 Sharpe 差 0.076（剛跨「Sharpe 退步 > 0.05 fail」門檻），但 47-cohort
樣本 noise 也在這個量級，**production 維持 10 或調 11 均可，不要往 15+ 加**。

### ml_score 漂移檢查（為什麼不能用絕對 threshold）

LGBMRanker 的 score 不是 calibrated probability，跨 cohort 會漂移：

| 區段 | median | p90 |
|---|---|---|
| 早期 1/3 (2022-07 → 2023-12) | -2.82 | -0.92 |
| 近期 1/3 (2025-05 → 2026-04) | -2.12 | -0.44 |
| Δ in std units | +1.69σ | +1.24σ |

→ **固定 `ml_score > X` 的 threshold 不可行**。per-cohort 百分位（top-K%）
等價於 top-N，沒額外資訊。剩下唯一可走的路是相對於歷史的 walk-forward
percentile gate。

### Regime diagnostic（46 cohort, signal vs realized return correlation）

| 信號（at cohort entry） | Pearson | Spearman | Q5-Q1 spread |
|---|---|---|---|
| **score_topN_mean** | **+0.402** | +0.313 | +10.47% |
| **score_p90** | +0.369 | +0.246 | **+13.18%** |
| score_median | +0.272 | +0.169 | +7.01% |
| ret_60d_pct (TWII) | +0.168 | +0.223 | +7.38% |
| close_vs_ma20_pct | +0.123 | +0.158 | +4.65% |
| ret_20d_pct | +0.081 | +0.159 | +1.46% |
| **vol_20d_ann_pct** | +0.369 | **+0.128** | +5.59% |
| **ma20_vs_ma60_pct** (現產線 regime 偵測用的) | **+0.047** | +0.110 | +0.02% |

關鍵發現：

- **score-based 訊號完勝 trend / vol 訊號**。模型自己的信心（top10 score
  mean、p90）是最強的下個月報酬預測子。
- **vol_20d Pearson +0.369 是 outlier artifact** — Spearman 只 +0.128，
  幾乎全是 1–2 個高 vol cohort 剛好大贏帶起來。Vol-based gate 不可信。
- **MA20/MA60 spread Pearson +0.047** ≈ 零。`run_rolling.py:80-140` 的 MA-cross
  regime 偵測（commit 226b6be 之前用來做 Bear-skip 的那個）作為連續訊號
  完全無預測力，並非「Bear 月仍正報酬」而是 signal 本身就沒用。
- Bull/Bear/Sideways label 均值：Bear=+4.57% / Sideways=+8.24% / Bull=+10.16%。
  Bear 仍正、confirm 226b6be 拿掉硬 skip 的判斷。

### Walk-forward score_p90 gate — 表面 Sharpe +0.50，全是 hindsight

對「score_p90 < walk-forward 歷史 P%」做 (a) 整月 skip、(b) 降到 top_5 兩種
gate。Baseline = top_n=10 同 4Y 範圍。

| Scenario | Triggers | Sharpe | Total PnL | Worst month | Max DD |
|---|---|---|---|---|---|
| baseline_top10 | 0 | 2.964 | 3.96M | -21.56% | -228K |
| **skip @ 10p** | **1** | **3.464** | 4.17M | **-6.44%** | **-83K** |
| skip @ 20p | 5 | 3.241 | 3.99M | -6.44% | -83K |
| skip @ 30p | 7 | 3.058 | 3.82M | -6.44% | -83K |
| reduce @ 20p | 5 | 2.931 | 4.00M | -23.85% | -132K |
| reduce @ 30p | 7 | 3.007 | 4.01M | -23.85% | -132K |

20p threshold 5 個 trigger 點：

| playbook | score_p90 | wf percentile | baseline_ret_pct |
|---|---|---|---|
| 2023-02-11 | -1.19 | 14.3% | +10.5% ← 跳了就賠 |
| 2023-03-11 | -1.39 | 12.5% | +6.2% ← 跳了就賠 |
| 2024-12-11 | -1.12 | 17.2% | -1.4% |
| 2025-01-11 | -1.17 | 16.7% | +3.0% ← 跳了就賠 |
| 2025-03-11 | -1.21 | **6.3%** | **-21.6%** ← 唯一真實 hit |

**精準度 1/5**，gate 看似 Sharpe +0.50 全是 2025-03 那一個月帶起來的。
2025-03 是 2025-04-01 國際政治事件 (exogenous shock)，模型 ml_score 不可能
事前知道，gate 抓到純屬巧合 — 見 memory `project_2025_03_political_shock.md`。

### Robustness：排除 2025-03 後

| Scenario (no 2025-03) | Sharpe | Δ vs baseline |
|---|---|---|
| baseline_top10 | 3.464 | — |
| skip @ 10p | 3.464 | 0（10p 不再觸發） |
| skip @ 20p | 3.241 | -0.22 ❌ |
| skip @ 30p | 3.058 | -0.41 ❌ |
| reduce @ 20p | 3.493 | +0.029（< fail 門檻） |
| reduce @ 30p | 3.565 | +0.10 ⚠️ in-sample 挑點 |

**baseline 自己只因為移除 2025-03 一個月就從 2.964 → 3.464（+0.50）**，
全部 gate alpha 都建在這個 outlier 上。剝離後 skip 變體 net 負貢獻、reduce
變體幾乎平。

### Decision

- ❌ **不部署任何 score_p90 / vol / MA-cross 的 regime gate**。沒有穩定 alpha。
- ✅ **top_n 維持 10**（或 9/11 同等地位），不要往 15+ 移。
- ✅ **2025-03 是 exogenous shock**，未來做 regime/gate 評估時要列入 outlier
  exclusion；不要用 ml_score 偽裝風控。對策若需要請走外部對沖。
- ✅ **下次有人想做 regime gate 之前**，先 ablation 把 2025-03 排除再看 Sharpe
  改善 — 若 < 0.05 直接拒絕。

## Open Directions (未做)

1. **Multi-seed ensemble for α=0.7 mixed label** — sweep 顯示 label→model
   有 noise，5-seed average 可能拍上 0.7 的 Sharpe 上限
2. **P3 / P5 features + α=0.7 label** — 兩個都在 fwd_return label 下退
   Sharpe，但在 mixed label 下可能不會（沒測）。Informative follow-up
3. **更激進 label**：todo 原寫的 multi-task（fwd_return + sharpe + mdd
   同時訓練、loss weighted）— 工程複雜度高
4. **Position sizing by vol** — 不動 model，按持股 vol 反比 weight
   capital，平滑月度 std
5. **P4 (streak→cumulative net_buy), P6 (大盤 regime), P7 (cohort rank)**
   — 本輪沒做完，但 P6 含 taiex_vol_20d 直接跟 P3 教訓衝突，預期高風險
