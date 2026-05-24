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
