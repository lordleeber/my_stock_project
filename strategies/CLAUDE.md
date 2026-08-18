# strategies AI Guide

## Scope
- Work only inside `strategies/`.
- Responsibility: monthly candidate dataset + LGBMRanker selection model training/scoring.

## Date Convention (READ FIRST)

CLI 一律收 `--date YYYY-MM-DD`，目錄結構也一律 `<YYYY-MM-DD>/`。**不再用 `--year/--month`**，跟 train_eps 風格一致。

**三個 date 概念 — 不要混用**：

| Term | Belongs to | Format | Meaning |
|---|---|---|---|
| `playbook_date` | **target / train_through cohort** | YYYY-MM-DD（CLI `--date` 直接拿這個值；同時也是目錄名） | 該 cohort 實際跑訓練/評分那天，= cutoff +1 calendar day |
| `cutoff_date` | **target cohort** | YYYY-MM-DD | 該 cohort 的 PIT 特徵截斷日（公告日）；step1 SQL 用 `WHERE date <= cutoff_date` |
| `train_through_playbook_date` | **selection model** | YYYY-MM-DD | model 訓練資料涵蓋到的最後 cohort 的 `playbook_date`（= 該 cohort cutoff +1） |

`cutoff` 這個字根 **只配 target**；model 端永遠用 `train_through_*`。

> step5 scores **target playbook_date 2026-05-16 (cutoff 2026-05-15)** using the **train_through_playbook_date=2026-04-11 (cutoff 2026-04-10)** model.

兩個 playbook_date 差一個 cycle — 同一個日期可以同時是 target_M 的 `playbook_date` 跟 target_{M+1} 訓練那顆 model 的 `train_through_playbook_date`，視場景而定。

Examples of correct narration:

- ✅ "cohort 2026-04-11 (cutoff 2026-04-10)"
- ✅ "step5 scores target 2026-05-16 using train_through=2026-04-11 model"
- ✅ "training set covers 2021-08-16 → 2026-04-11, ~58 cohorts"
- ❌ "April model" / "2026/04" alone — which date? target, or train_through? 用 playbook_date 講
- ❌ "model's cutoff_date 2026-04-10" — 用詞錯誤，model 端要用 `train_through_playbook_date`（或想強調 PIT 截斷時 `train_through_cutoff_date`）

### The canonical date formula

Single source of truth: `strategies/shared_config.py`（re-exports `train_eps.shared_config`）。

```python
# playbook_date = 公告日 + 1
day = 16 if month in {5, 8, 11} else 11
# cutoff_date = playbook_date - 1 calendar day
```

跟 train_eps 共用同一個 `playbook_run_date` / `parse_playbook_date`。CLI date 解析失敗或非 canonical（例如誤傳 2026-04-10 = 公告日）會直接 raise。

`daily_quotes` 查詢用 `date <= cutoff_date` 取最新一筆，所以 cutoff_date 撞到假日時 **實際** PIT snapshot 會落在前一個交易日（記在 `dataset_strategy.csv.quote_date`）。例如：

| playbook_date (cohort label) | Nominal cutoff_date | Actual quote_date (DB PIT) | entry_date (next trading day) |
|---|---|---|---|
| 2025-10-11 | 2025-10-10 (連假) | 2025-10-09 | 2025-10-13 |
| 2025-11-16 | 2025-11-15 (週六) | 2025-11-14 | 2025-11-17 |
| 2026-01-11 | 2026-01-10 (週六) | 2026-01-09 | 2026-01-12 |

If a narration needs to distinguish the **calendar formula date** vs the **actual PIT date**, use "cutoff_date YYYY-MM-DD (quote_date YYYY-MM-DD)" or just pull `quote_date` from the artifact directly.

### Five dates per cohort

Every cohort owns five flow-through dates:

| Date | Defined by | Stored where | Meaning |
|---|---|---|---|
| `playbook_date` | `playbook_run_date(year, month)` (cutoff +1) | directory name `<YYYY-MM-DD>/`; CLI `--date` | cohort 識別與目錄/路徑命名 |
| `cutoff_date` | `cutoff_date_from_playbook(playbook_date)` (playbook −1) | implicit; equal to `quote_date` on trading days | feature PIT snapshot |
| `quote_date` | `daily_quotes` MAX(date ≤ cutoff_date) | `dataset_strategy.csv.quote_date` | actual feature snapshot day |
| `entry_date` | next trading day after `cutoff_date` | `dataset_strategy.csv.entry_date` | open price used to enter |
| `exit_date` | next-cohort `entry_date` − 1 trading day | `feature_return_analysis.csv.exit_date` | open price used to exit, defines `fwd_return_pct` |

So a single cohort label `2026-04-11` silently references **five dates** (2026-04-11 / 2026-04-10 / 2026-04-10 / 2026-04-13 / 2026-05-15). Always be explicit about which one you mean.

### Walk-forward terminology

| Term | Belongs to | Concretely |
|---|---|---|
| **Target cohort** M | step5 inference | The cohort being scored. Identified by `playbook_date` `D_M`. |
| **train_through** = M−1 | the model | The selection model used to score target M was trained with `playbook_date ≤ D_{M−1}` cohorts. Its `train_through_playbook_date` is `D_{M−1}`. |
| **Training data range** | the model | All cohorts from 2021-08-16 through M−1 inclusive — **not a single month**, a cumulative pool with upper bound = `train_through_playbook_date`. |

Time-wise: the `train_through=M−1` model is **trained on target cohort M's `cutoff_date`** — that's the same trading day where cohort M−1's `exit_date` realises and its `fwd_return_pct` becomes the model's freshest training label. So one calendar date plays two roles simultaneously: target M's `cutoff_date` AND the moment after which train_through=M−1 model is trainable. Always disambiguate by saying which role you mean.

## Pipeline Layout

All CLI args use `--date YYYY-MM-DD`（playbook_date，cutoff +1）；省略則自動鎖到 `latest_playbook_date()`。

| Step | Script | Output |
|---|---|---|
| 1 | `step1_prepare_data.py --date D` | `output/<D>/dataset_strategy.csv` (~38 cols, after ttm/volume filter) |
| 2 | `step2_finalize_strategy.py --date D` | enrich `dataset_strategy.csv` with technical/revenue/EPS-prediction features (~69 cols); write `trade_candidates.csv`（診斷用，不在生產路徑上——見 [Step2 Adds](#step2-adds)） |
| 3 | `step3_analyze_feature_returns.py` | `feature_return_analysis.csv` (fwd_return ground truth)，掃描所有 `output/<D>/` |
| 4 | `step4_train_selection_model.py --date D` | `models_selection/<D>/selection_model.pkl` + feature_importance + latest.json（`D` = train_through_playbook_date） |
| 5 | `step5_score_and_publish.py --date D` | `models_selection/<D>/candidates_scored.csv` (final picks by `ml_rank`，`D` = target_playbook_date) |

Batch variants (`stepN_batch_*.py`) loop the same logic over `--start-date` / `--end-date` ranges of canonical playbook dates.

## Data Sources (DB tables)

Step1 reads from:

| Table | Purpose | Filter |
|---|---|---|
| `quarterly_reports_xbrl` | anchor & pre-anchor quarter wide-format facts (revenue_q, net_income_q, pretax_income_q, non_op_income_q, capital, eps_q) | `date IN (anchor_q, pre_anchor_q, ...)` AND `period_type='quarter'` |
| `balance_sheet_xbrl` | total_assets (1XXX), total_liabilities (2XXX), total_equity (3XXX), retained_earnings (3300) | `date=anchor_q` AND `period_type='as_of'` AND `account_code IN (...)` |
| `cash_flow_xbrl` | operating cash flow (AAAA, accumulated) — converted to single-quarter | `date IN (anchor_q, pre_anchor_q)` AND `period_type='accumulated'` AND `account_code='AAAA'` |
| `stock_info` | name + industry + canonical market | LEFT JOIN, fallback to `quarterly_reports_xbrl.market` |
| `monthly_revenue` | monthly revenue features | `date IN mctx.mr_dates` |
| `daily_quotes` | latest close/volume on or before cutoff_date | `date <= cutoff_date` AND `market=...` |
| `valuation_daily` | roe_official, pe_percentile_official (PIT-aligned) | latest per symbol where `date <= end_date` |
| chip/sentiment tables | `foreign_holding`, `trust_holding`, `dealer_holding`, `shareholding_concentration`, `margin_pressure_analysis`, `short_interest_analysis` | per-feature SQL |

> Old tables `income_statement` / `balance_sheet` / `cash_flow` are deprecated. Step1 no longer touches them.

## Anchor Quarter Cash-Flow Conversion

`cash_flow_xbrl` only stores `period_type='accumulated'` (year-to-date values). For the anchor quarter's single-quarter OCF:

```
anchor_ocf = (anchor_q acc) − (pre_anchor_q acc)  if anchor_q is Q2/Q3/Q4
           = anchor_q acc                         if anchor_q is Q1 (no Y-T-D before Q1)
```

The SQL uses `CASE WHEN RIGHT(anchor_q, 2) = 'Q1' THEN ... ELSE ... END` to handle the Q1 special case. `pre_anchor_q` for a Q1 anchor is the prior year's Q4, whose accumulated value is the full-year — subtracting it would yield garbage.

## Market Label Inconsistency

About 1–2% of symbols have different market labels across tables (e.g., `quarterly_reports_xbrl.market='sii'` but `stock_info.market='otc'`, or symbol missing from `stock_info` altogether). Step1's filter uses `COALESCE(stock_info.market, quarterly_reports_xbrl.market) = '{market}'` so each symbol appears in exactly one market run. The downstream `pd.concat` of sii+otc produces a single deduplicated universe.

## Filters in Step1

| Filter | Threshold |
|---|---|
| TTM EPS proxy | `ly_target_eps + pre_anchor_eps + anchor_eps ≥ 2.0` |
| Min 20-day average volume | `avg_volume_lots_20d ≥ 400`（近 20 個交易日均量，張） |

> 2026-07 起流動性門檻由「單日 `volume_lots > 500`」改為 20 日均量——單日 snapshot
> 對剛好安靜/爆量一天的股票雜訊太大。單日 `volume_lots` 仍保留為 ranker 特徵
>（`FEATURE_COLS` 不變），此門檻只影響候選宇宙。

Hard filter values are constants in `step1_prepare_data.py` near the top — change with care; backtester reproducibility depends on them.

## Step2 Adds

- Technical: MA5/10/20/60/240, RSI6/12, KD, MACD, BB position, volume ratios
- Revenue momentum: YoY 1m / 3m avg / cum / mom / accel / positive streak
- EPS prediction merge: `pred_lgb_delta` from `models_eps/<D>/predictions_results.csv`，路徑直接用 strategies CLI 的 `--date D`（與 train_eps `--date` 同一 canonical playbook date）
- 預期 TTM EPS 成長三特徵（取代舊版單一 `pred_upside_pct`）：
  - `base_eps_growth_pct = 100 × (anchor_eps − ttm_rolloff_eps) / ttm_eps`（純會計，含去年同季 base effect）
  - `ml_eps_delta_pct    = 100 × pred_lgb_delta / ttm_eps`（純 train_eps model 訊號）
  - `eps_growth_total_pct = base + ml`（= 舊版 `pred_upside_pct`，smoothed 主訊號）
    - **語意：下一季財報公布後，TTM EPS 預期變動幾 %。** TTM 視窗每季往前滾一格，進來一季新的、踢掉一季舊的；本欄 = `(預測的新進季 − 被踢掉的季) / 現在的 TTM`。所以 **`<= 0` 代表預期滾動四季 EPS 會縮水或持平**。
    - 例（2026-07 cohort，踢掉 2025Q2）：6187 萬潤 TTM 15.26，出去 4.16、進來 3.37+0.507=3.88 → 新 TTM ≈ 14.98 → **−1.86%**。
    - ⚠️ **低基期陷阱**：`ttm_rolloff_eps` 為負（去年同季虧損）時，移除一個負數會機械式拉高 `base`。例：2344 華邦電踢掉的 2025Q2 是 −0.29，`base` 因此衝到 +75%，但那不等於本業動能。audit 結論是 58 個 cohort 中 `base` 解釋約 85% 的排序變異——這正是當初把單一 `pred_upside_pct` 拆成 base / ml 兩欄的原因。
  - 其中 `ttm_rolloff_eps` 是該 playbook 月份 TTM 視窗即將踢出去的那季 EPS，月份對應與 step1 `compute_ttm_eps_by_month` 一致：02-04→`ly_q1_eps`、05-07→`ly_q2_eps`、08-10→`ly_q3_eps`、11-01→`ly_q4_eps`
  - 為什麼留三欄？base 跟 ml 算術上 Spearman ≈ −0.5（高 base 通常伴隨負 ml — ML 對極端 anchor 預測 mean reversion），LightGBM 學「兩特徵相加」靠 tree splits 拼湊效率較差。實測 (audit) 拿掉 `total` 只留 base+ml 時 backtest 4 年 PnL 從 +3.82M 掉到 +3.24M (−15%)；補回 `total` 後 PnL 恢復 +3.82M、win_rate 微升、median return 從 5.10% 升到 5.69%，且 `ml_eps_delta_pct` 仍以獨立 feature 進入 top 7 = ML 訊號真的有額外可歸因價值。
- `entry_date` = the cutoff_date's next trading day

`trade_candidates.csv` filters `dataset_strategy.csv` by `eps_growth_total_pct > 0`（與舊版 `pred_upside_pct > 0` 數學等價）和 sorts by `eps_growth_total_pct` desc；同時暴露 `base_eps_growth_pct` / `ml_eps_delta_pct` 兩欄方便歸因 picks 是 base-driven 還是 ML-driven。

> ### ⚠️ `trade_candidates.csv` 不在生產路徑上，那道 `> 0` 過濾沒有生效
>
> `run_rolling.py` 讀的是 `models_selection/<D>/candidates_scored.csv`（`run_rolling.py:145`、`:291`），**從不讀 `trade_candidates.csv`**。目前只有 `compare_versions.py`（版本比對診斷）與 `step2_batch` 的 `--skip-existing` 存在性檢查會用到它。
>
> 因此 `eps_growth_total_pct > 0` 這道濾網**不會影響選股**：step5 讀的是未過濾的 `dataset_strategy.csv`，全部候選一律打分，`candidates_scored.csv` 的列數等於候選池大小。
>
> 實測（2026-08 重建後全 49 個 cohort）：top-25 合計 1,225 個標的，其中 **71 個（5.8%）`eps_growth_total_pct <= 0`**，分布在 32/49 個 cohort，單月最多 5 檔。也就是說 ranker 確實會把「預期滾動 EPS 衰退」的股票排進前 25，而且一直如此。
>
> 這是設計問題不是 bug：ranker 有 51 個特徵，EPS 成長只是其中之一。要不要把 `> 0` 搬進 step5 變成硬性門檻，需要重跑對照才能判斷好壞。在做出決定之前，**不要以為那道濾網有在保護選股**。

### `--entry-date` Override (step2)

Default behaviour: `resolve_entry_date` queries `daily_quotes` for the first trading day ≥ `cutoff_date + 1`. If the DB has no such row, step2 **raises** (commit 866fc36) — this catches the case where `cutoff` was Friday and `entry_date` is the following Monday but the Monday `daily_update.sh` has not yet run.

Override:
```bash
venv/bin/python3 strategies/step2_finalize_strategy.py \
  --date 2026-05-16 --entry-date 2026-05-18
```

When supplied, step2 skips the DB check and stamps the given date into the `entry_date` column. It does **not** affect features: technical and revenue features are fetched `WHERE date <= cutoff_date`, so their content is the same whenever you run. **Caller is responsible** for ensuring the override is a real trading day (no weekend / holiday) — `entry_date` is the entry price and `fwd_return` anchor.

### ⚠️ Feature as-of is `cutoff_date` — never `entry_date`

`fetch_technical_features` / `fetch_revenue_features` take an `as_of_date` and return the latest row `<= as_of_date`. **It must be `cutoff_date`.**

Passing `entry_date` looks harmless in a live run: `entry_date` is in the future, the DB physically has no rows for it, so the query falls back to the `cutoff_date` row anyway. But that PIT guarantee comes from the wall clock, not the code. Re-run the same cohort later — a batch rebuild, a restore, a backtest refresh — and the DB now covers `entry_date`, so the very same code silently picks up data that was not knowable at decision time.

This was live until 2026-08. Effects measured on the 2026-07-11 cohort:

- **26 of the selection model's 51 features** shift (21 technical/chip + 5 revenue).
- 2344's `ma5` moves from 07-09's `177.3` to 07-13's `173.8`; 355–359 of 359 names change.
- `close_vs_ma*` mixed two dates in one ratio — `close` came from step1 (`quote_date`) while the MA came from `entry_date`, producing a value matching no real market state.
- 48 of 49 stored cohorts had been rebuilt in batch on 2026-07-11, so **the training set carried entry-date features while live inference carried cutoff-date features** — a systematic train/serve skew.

`step2` calls `assert_features_not_beyond_cutoff()` on the **actually fetched rows**: `fetch_technical_features` / `fetch_revenue_features` return audit columns (`tech_snapshot_date` / `rev_max_publish_time`, dropped after the check). The run fails if:

| condition | message points at |
|---|---|
| tech snapshot > `cutoff_date` | as-of 被改回 `entry_date`（look-ahead 本體） |
| tech snapshot < `max(quote_dates)` | calculator 未跑完，`technical_indicators` 落後 `daily_quotes`（重跑 step1 沒用） |
| tech snapshot > `max(quote_dates)` | step1 產出後 DB 又匯入新資料，請重跑 step1 |
| any revenue `publish_time` > cutoff | 決策當下拿不到的申報進了特徵 |
| 任一稽核欄全空 | 驗不了 = 失敗（fail-closed） |

比對 step1 的 `quote_date` 用 **等值於 `max(quote_dates)`**，不是集合成員判定：`quote_date` 是 per-symbol 的（step1 `PARTITION BY d.symbol`），停牌股會讓集合變多值，用 `in` 的話技術指標整批落後時只要撞上某檔停牌股的舊 `quote_date` 就會被放行。

Point the as-of back at `entry_date` and the first historical rebuild fails loudly. **A live run with the same regression still passes** — at that moment the DB genuinely has no post-cutoff rows, so there is nothing for a runtime check to detect. 補上這個缺口的是 `strategies/tests/test_feature_asof_guard.py`：assert 是純 DataFrame 函式（不收 engine、不發查詢），所以回歸在 commit 當下就會被測試攔下，不必等到第一次歷史重跑。

Do not weaken that check, and do not replace its inputs with independent DB queries — asserting on anything other than the fetched rows is how the previous version of this guard ended up vacuous.

See [`MONTHLY_PLAYBOOK.md` Q5](../MONTHLY_PLAYBOOK.md) for the operational scenario.

## Walk-Forward Selection Model

- Models stored at `models_selection/<train_through_playbook_date>/`（YYYY-MM-DD 直接當目錄名）
- Scoring target cohort M (step5) picks the latest model whose `train_through_playbook_date < target_playbook_date`
- Training the `train_through=M−1` model requires step3 fwd_return reaching cohort M−1, which requires step1+2 for cohort M (entry_date) to be done first

### Model hyperparameters (LGBMRanker)

Production config (step4 / step4_batch defaults): `n_estimators=500, learning_rate=0.03,
num_leaves=15, min_child_samples=15, reg_alpha=0.05, reg_lambda=0.1, n_bins=10, seed=42,
n_seeds=10` (10-seed ensemble, seeds 42–51, scored with `--ensemble-agg score`).

> Since 2026-06 **step4-single defaults match step4_batch** (previously single defaulted to
> `n_bins=5, reg_alpha=0, reg_lambda=0`, silently diverging) — so the bare
> `step4 --date PREV` call in `schedules/playbook_run.sh` now produces exactly the
> backtested model.

> **⚠️ `num_leaves=15 / min_child_samples=15` is a deliberate low-capacity choice — do
> NOT bump back to the old `31 / 5` without re-validating across seeds.** During the
> ISSUE #2 valuation_daily fix we found the `31/5` ranker was **fragile**: a ~0.3% change
> in training features (the corrected loss-making-stock `roe_official` / `pe_percentile_official`)
> reshuffled ~26% of picks and dropped the 38-basis monthly Sharpe from ~0.70 to ~0.62
> — purely a model-variance amplification (mean return / PnL were flat; std rose). Lowering
> capacity (either `num_leaves↓` or `min_child_samples↑` — they're substitutes) restores
> the Sharpe distribution to baseline: over **30 seeds**, `15/15` gives mean Sharpe **0.707**
> (95% CI [0.690, 0.725], 90% of seeds within the 0.05 fail-threshold) at PnL ≈ baseline.
> `seed=42` is a fixed a-priori default (not selected on score); single-seed Sharpe ranges
> ~0.64–0.83, so judge configs by the **distribution**, not one run.

> **⚠️ 上面與下面所有 ~0.70 / ~0.716 / 0.68–0.74 的 Sharpe 絕對水準，都是 2026-08-02
> 修掉 `entry_date` look-ahead **之前**量的，已不是現行基準。** 同一組舊 artifacts 用
> 修正後的 code 重跑（`--end-date 2026-07-11`, top-25, 40 cohort）是 **0.5453**；
> 保留舊 as-of 的對照跑則重現 0.7017（`backtester/output/rolling_old_entrydate/`）。
> 2026-08-18 個體財報回補後、同區間同設定是 **0.5526**。
> 這些段落的**相對**結論（低容量 `15/15` 優於 `31/5`、ensemble 消掉 seed 樂透）不受影響，
> 失效的只是絕對數字。`scripts/validate_ensemble.py` 的 PASS 門檻（`center ~0.707`、
> `PnL std ~9.8%`）若照舊跑會全面誤判失敗，重跑前要先重設基準。

### Multi-seed ensemble (`--n-seeds`)

Because single-seed Sharpe is a lottery (sd ~0.049 over 30 seeds), step4 trains a
**K-seed ensemble** (default K=10) and step5 averages their predictions, pulling the result
to the distribution centre (variance ~1/√K) instead of betting on one seed.

- `step4 --n-seeds K` trains seeds `[seed, seed+1, …, seed+K-1]` (production `--seed 42
  --n-seeds 10` = seeds 42–51). `step4_batch` forwards `--n-seeds`.
- **Payload format is dual / backward-compatible**:
  - `n_seeds == 1` (default) → `{"model": <ranker>, "feature_cols": [...]}` — **unchanged**, picks byte-stable.
  - `n_seeds > 1` → `{"models": [m1..mK], "feature_cols": [...], "seeds": [...], "ensemble": True}`.
  - step5 detects either, and still reads legacy on-disk `{"model": ...}` pkls.
- `step5 --ensemble-agg {score,rank}` (default `score`): `score` = mean of raw predict
  scores; `rank` = mean of per-model ranks with `ml_score = -mean_rank` (kept monotone-
  increasing so `run_rolling`'s sort-by-`ml_score` is unaffected). No-op for single-model
  payloads. `candidates_scored.csv` records `scored_by_ensemble_k` / `_seeds` / `_agg`.
- `--models-root` (step4 / step4_batch / step5 / step5_batch) redirects the model dir so
  parallel/disjoint runs don't collide; default stays `models_selection/`.
- Validation harness: `scripts/validate_ensemble.py` (3 disjoint seed groups × K × agg →
  full walk-forward + backtest; writes `backtester/output/val/SUMMARY.md`).

> **Production runs the 10-seed ensemble as of 2026-06** (validated: 12 disjoint-group runs
> all landed at monthly Sharpe ~0.68–0.74, center ~0.716 ≈ baseline, PnL flat — the
> single-seed lottery is gone). K=10+score chosen on theory (1/√K variance reduction);
> the 3-group spread was too noisy to rank K=5 vs K=10. See
> `project_ensemble_validation_2026_06`. To recover legacy single-seed behaviour pass
> `--n-seeds 1`.

Concrete example for target playbook_date 2026-05-16 (cutoff 2026-05-15):

1. 2026-05-15 (Fri): target 2026-05-16's `quote_date` snapshot taken; cohort 2026-04-11's `exit_date` realises here too → `fwd_return_pct` for 2026-04-11 cohort becomes computable.
2. step3 re-runs → `feature_return_analysis.csv` now includes 2026-04-11 (entry 2026-04-13 → exit 2026-05-15) rows.
3. step4 trains `train_through_playbook_date=2026-04-11 (cutoff 2026-04-10)` selection model using `playbook_date ≤ 2026-04-11` rows (2021-08-16 → 2026-04-11, ~58 cohorts).
4. step5 scores target 2026-05-16 candidates with that `train_through=2026-04-11` model. Walk-forward picks it via `train_through_playbook_date < target_playbook_date`.

See [`MONTHLY_PLAYBOOK.md`](../MONTHLY_PLAYBOOK.md) for the strict ordering rule.

## ⚠️ `models_selection/<DATE>/` Directory Has Dual Meaning

Same directory, two files with different temporal labels:

| File | `DATE` interpretation |
|---|---|
| `selection_model.pkl` | DATE is **train_through_playbook_date** — training used data up to that cohort's fwd_return |
| `candidates_scored.csv` | DATE is **target_playbook_date** — scored by a model with **train_through_playbook_date < DATE** (walk-forward) |

Example: `models_selection/2026-04-11/candidates_scored.csv` lists target 2026-04-11 candidates scored by `models_selection/2026-03-11/selection_model.pkl` (train_through_playbook_date=2026-03-11, cutoff 2026-03-10). The 2026-04-11 model in the same directory was trained later (at 2026-05-15, after cohort 2026-04-11's fwd_return realised) and is used for target **2026-05-16** candidates.

To remove ambiguity, step5 writes two columns into `candidates_scored.csv`:

- `scored_by_train_through_playbook_date` (value like `"2026-03-11"`) — the model's directory name = its train_through_playbook_date
- `scored_by_train_through_cutoff_date` (value like `"2026-03-10"`) — that cohort's `cutoff_date` (公告日)

so the model source is always self-evident from the file alone, without consulting any other artifact.

> **Legacy schema note**: artifacts in `models_selection_old/` use older names — `latest.json["cutoff"]` / `scored_by_model_cutoff` / `scored_by_train_through` / `scored_by_train_through_date` — different namespaces over time. `compare_versions.py` reads with fallbacks.

## EPS Column Naming in `dataset_strategy.csv`

Two prefix families distinguish year:

| Prefix | Meaning |
|---|---|
| `ly_*` | **last year** — Q1/Q2/Q3/Q4 of `target_year − 1` |
| `ty_*` | **target year** — Q1/Q2 of `target_year` (the year being predicted) |
| `anchor_*` | The most recent fully-published quarter as of cutoff |
| `target_*` | The quarter being predicted (NaN for live inference; actual value in historical batch) |

Note `ty_q1_eps` / `ty_q2_eps` may equal `anchor_eps` or `target_eps` depending on the playbook month — see `build_quarter_context` in `train_eps/step1_prepare_data.py` for the exact mapping per month. The columns hold the raw quarter EPS regardless of role.

Legacy column `prev_q4_eps` (always identical to `ly_q4_eps`) was removed; downstream should use `ly_q4_eps`.

## Quote Snapshot Columns

`dataset_strategy.csv` carries the **latest daily-quote snapshot at or before cutoff_date** (not a quarterly value):

| Column | Meaning |
|---|---|
| `quote_date` | The trading date of the snapshot (typically equals cutoff_date unless cutoff falls on a non-trading day) |
| `close` | Close price on `quote_date` |
| `volume_lots` | Volume in lots (張，= shares ÷ 1000) on `quote_date` |
| `avg_volume_lots_20d` | 近 20 個交易日均量（張；上市未滿 20 日者取現有筆數平均）。僅供 step1 流動性 filter，非 ranker 特徵 |
| `ttm_eps` | Trailing-twelve-month EPS computed from quarterly EPS columns per the playbook month's anchor selection |
| `pe_current` | `close / ttm_eps` |

Legacy columns `q3_close` / `q3_date` / `q3_volume` (the `q3_` prefix was an internal SQL CTE artifact, **not** related to fiscal Q3) and `target_volume` / `ttm_eps_official` (step1 raw names) were removed because they sat alongside true quarterly columns (`ly_q3_eps`, etc.) and invited misreading. The canonical names above are emitted directly by step1; step2 no longer adds duplicate aliases.

## Rules

- **Date narration**: see [Date Convention](#date-convention-read-first). CLI args and directory layouts 都用 `YYYY-MM-DD`（playbook_date）；prose 提到 cohort 也一律寫具體日期，不要寫 `YYYY/MM`。
- **Date terms**: `cutoff_date` 只配 target / cohort；`train_through_playbook_date` 配 selection model（必要時對應 `train_through_cutoff_date`）。不要寫 "model's cutoff_date"。
- Do NOT add new SQL paths to deprecated tables (`income_statement`, `balance_sheet`, `cash_flow`, `quarterly_reports`).
- Do NOT commit generated `output/`, `models_selection/`, or csv/pkl artifacts unless asked.
- When adding XBRL account_codes, verify coverage across periods (some codes appear sparsely; check `data/processed/xbrl_codebook.csv`).
