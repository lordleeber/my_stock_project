# strategies AI Guide

## Scope
- Work only inside `strategies/`.
- Responsibility: monthly candidate dataset + LGBMRanker selection model training/scoring.

## Date Convention (READ FIRST)

**Anywhere you talk about a "month" in this module — in code comments, log lines, PR descriptions, chat, this doc — append the concrete `YYYY-MM-DD`.** A bare `YYYY/MM` label is ambiguous: it can mean cohort, target, model training upper bound, or holding period. The date disambiguates.

**Two distinct date terms — do NOT mix them**:

| Term | Belongs to | Meaning |
|---|---|---|
| `cutoff_date` | **target cohort** | 該 cohort 的 PIT 特徵截斷日；step1 / step5 「站在這天」評分。等於 `dataset_strategy.csv.quote_date`（差別只在假日修正）。 |
| `train_through_date` | **selection model** | 該 model 訓練資料涵蓋到的最後 cohort 的 `cutoff_date`。等於「model 看過資料看到哪天」。 |

`cutoff` 這個字根 **只配 target**；model 端永遠用 `train_through`。同一句話可以同時出現兩個，但不會混淆：

> step5 scores **target 2026/05 (cutoff_date 2026-05-15)** using the **train_through=2026/04 (train_through_date 2026-04-10)** model.

兩個日期差一個 cycle (cohort M 的 cutoff_date vs cohort M−1 的 cutoff_date) — 同一個日期可以同時是 target_M 的 cutoff_date 跟 target_{M+1} 訓練那顆 model 的 train_through_date，視場景而定。

Examples of correct narration:

- ✅ "cohort 2026/04 (cutoff_date 2026-04-10)"
- ✅ "step5 scores target 2026/05 (cutoff_date 2026-05-15) using train_through=2026/04 (train_through_date 2026-04-10) model"
- ✅ "training set covers 2021/08 (2021-08-10) → 2026/04 (2026-04-10), ~45 cohorts (train_through_date = 2026-04-10)"
- ❌ "April model" / "2026/04" alone — which date? cohort, target, or train_through?
- ❌ "model's cutoff_date 2026-04-10" — 用詞錯誤，model 端要用 `train_through_date`

### The canonical date formula

Single source of truth: `strategies/step1_prepare_data.py::model_release_date(year, month)`.

```python
day = 15 if month in {5, 8, 11} else 10
# 5/8/11 月是季報公告月（5/15、8/15、11/15）；其他月份是月營收公告（10 日）
```

`daily_quotes` 查詢用 `date <= cutoff_date` 取最新一筆，所以 cutoff_date 撞到假日時 **實際** PIT snapshot 會落在前一個交易日（記在 `dataset_strategy.csv.quote_date`）。例如：

| Label (cohort) | Nominal cutoff_date | Actual quote_date (DB PIT) | entry_date (next trading day) |
|---|---|---|---|
| 2025/10 | 2025-10-10 (連假) | 2025-10-09 | 2025-10-13 |
| 2025/11 | 2025-11-15 (週六) | 2025-11-14 | 2025-11-17 |
| 2026/01 | 2026-01-10 (週六) | 2026-01-09 | 2026-01-12 |

If a narration needs to distinguish the **calendar formula date** vs the **actual PIT date**, use "cutoff_date YYYY-MM-DD (quote_date YYYY-MM-DD)" or just pull `quote_date` from the artifact directly.

### Four dates per cohort

Every (year, month) cohort owns four flow-through dates:

| Date | Defined by | Stored where | Meaning |
|---|---|---|---|
| `cutoff_date` | `model_release_date(year, month)` | implicit; equal to `quote_date` on trading days | feature PIT snapshot |
| `quote_date` | `daily_quotes` MAX(date ≤ cutoff_date) | `dataset_strategy.csv.quote_date` | actual feature snapshot day |
| `entry_date` | next trading day after `quote_date` | `dataset_strategy.csv.entry_date` | open price used to enter |
| `exit_date` | next-cohort `entry_date` − 1 trading day | `feature_return_analysis.csv.exit_date` | open price used to exit, defines `fwd_return_pct` |

So a single cohort label "2026/04" silently references **four dates** (2026-04-10 / 2026-04-10 / 2026-04-13 / 2026-05-15). Always be explicit about which one you mean.

### Walk-forward terminology

| Term | Belongs to | Concretely |
|---|---|---|
| **Target cohort** M | step5 inference | The cohort being scored. Has `cutoff_date` `D_M`. |
| **train_through** = M−1 | the model | The selection model used to score target M was trained with `(year, month) ≤ M−1` cohorts. Its `train_through_date` is `D_{M−1}` (= cohort M−1's `cutoff_date`). |
| **Training data range** | the model | All cohorts from 2021/08 (2021-08-10) through M−1 inclusive — **not a single month**, a cumulative pool with upper bound = train_through_date. |

Time-wise: the `train_through=M−1` model is **trained on target cohort M's `cutoff_date`** — that's the same trading day where cohort M−1's `exit_date` realises and its `fwd_return_pct` becomes the model's freshest training label. So one calendar date plays two roles simultaneously: target M's `cutoff_date` AND the moment after which train_through=M−1 model is trainable. Always disambiguate by saying which role you mean.

## Pipeline Layout

| Step | Script | Output |
|---|---|---|
| 1 | `step1_prepare_data.py --year Y --month M` | `output/<Y>/<M>/dataset_strategy.csv` (40 cols, after ttm/volume filter) |
| 2 | `step2_finalize_strategy.py --year Y --month M` | enrich `dataset_strategy.csv` with technical/revenue/EPS-prediction features (76 cols); write `trade_candidates.csv` |
| 3 | `step3_analyze_feature_returns.py` | `feature_return_analysis.csv` (fwd_return ground truth) |
| 4 | `step4_train_selection_model.py --train-through-year Y --train-through-month M` | `models_selection/<Y>/<M>/selection_model.pkl` + feature_importance + latest.json |
| 5 | `step5_score_and_publish.py --year Y --month M` | `models_selection/<Y>/<M>/candidates_scored.csv` (final picks by `ml_rank`) |

Batch variants (`stepN_batch_*.py`) loop the same logic over month ranges.

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
| chip/sentiment tables | `foreign_holding`, `trust_holding`, `dealer_holding`, `large_holders`, `margin_sbl`, `margin_pressure_analysis`, `short_interest_analysis` | per-feature SQL |

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
| Min average volume | `volume_lots ≥ 500` |

Hard filter values are constants in `step1_prepare_data.py` near the top — change with care; backtester reproducibility depends on them.

## Step2 Adds

- Technical: MA5/10/20/60/240, RSI6/12, KD, MACD, BB position, volume ratios
- Revenue momentum: YoY 1m / 3m avg / cum / mom / accel / positive streak
- EPS prediction merge: `pred_lgb_delta`, `predict_target_eps`, `predict_target_price`, `pred_upside_pct` from `models_eps/<Y>/<M>/predictions_results.csv`
- `entry_date` = the cutoff_date's next trading day

`trade_candidates.csv` filters `dataset_strategy.csv` by `pred_upside_pct > 0` and sorts by upside.

### `--entry-date` Override (step2)

Default behaviour: `resolve_entry_date` queries `daily_quotes` for the first trading day ≥ `cutoff_date + 1`. If the DB has no such row, step2 **raises** (commit 866fc36) — this catches the case where `cutoff` was Friday and `entry_date` is the following Monday but the Monday `daily_update.sh` has not yet run.

Override:
```bash
venv/bin/python3 strategies/step2_finalize_strategy.py \
  --year 2026 --month 05 --entry-date 2026-05-18
```

When supplied, step2 skips the DB check and stamps the given date into the `entry_date` column. Technical and revenue features use `WHERE date <= ref_date` so they automatically fall back to the latest available data (= the `cutoff_date` row) — feature contents are identical to running after DB catches up. **Caller is responsible** for ensuring the override is a real trading day (no weekend / holiday).

See [`MONTHLY_PLAYBOOK.md` Q5](../MONTHLY_PLAYBOOK.md) for the operational scenario.

## Walk-Forward Selection Model

- Models stored at `models_selection/<train_through_year>/<train_through_month>/`
- Scoring target cohort M (step5) picks the latest model whose `train_through < M`
- Training the `train_through=M−1` model requires step3 fwd_return reaching cohort M−1, which requires step1+2 for cohort M (entry_date) to be done first

Concrete example for target 2026/05 (cutoff_date 2026-05-15):

1. 2026-05-15 (Fri): target 2026/05's `quote_date` snapshot taken; cohort 2026/04's `exit_date` realises here too → `fwd_return_pct` for 2026/04 cohort becomes computable.
2. step3 re-runs → `feature_return_analysis.csv` now includes 2026/04 (entry 2026-04-13 → exit 2026-05-15) rows.
3. step4 trains `train_through=2026/04 (train_through_date 2026-04-10)` selection model using `(year, month) ≤ 2026/04` rows (2021/08 → 2026/04, ~45 cohorts).
4. step5 scores target 2026/05 (cutoff_date 2026-05-15) candidates with that `train_through=2026/04` model. Walk-forward picks it via `train_through < target`.

See [`MONTHLY_PLAYBOOK.md`](../MONTHLY_PLAYBOOK.md) for the strict ordering rule.

## ⚠️ `models_selection/<Y>/<M>/` Directory Has Dual Meaning

Same directory, two files with different temporal labels:

| File | `M` interpretation |
|---|---|
| `selection_model.pkl` | M is **train_through** — training used data up to cohort M's fwd_return |
| `candidates_scored.csv` | M is **target** — scored by a model with **train_through < M** (walk-forward) |

Example: `models_selection/2026/04/candidates_scored.csv` lists target-2026/04 (cutoff_date 2026-04-10) candidates scored by `models_selection/2026/03/selection_model.pkl` (train_through=2026/03, train_through_date 2026-03-10). The 2026/04 model in the same directory was trained later (at 2026-05-15, after cohort 2026/04's fwd_return realised) and is used for target **2026/05 (cutoff_date 2026-05-15)** candidates.

To remove ambiguity, step5 writes two columns into `candidates_scored.csv`:

- `scored_by_train_through` (value like `"2026/03"`) — cohort-level label of the model used
- `scored_by_train_through_date` (value like `"2026-03-10"`) — that cohort's `cutoff_date`, the model's training upper bound

so the model source is always self-evident from the file alone, without consulting any other artifact.

> **Legacy schema note**: artifacts in `models_selection_old/` use the older names — `latest.json["cutoff"]` and `candidates_scored.csv.scored_by_model_cutoff` — same values, but the names mixed `cutoff` (a target-side term) with model-side semantics. The current schema separates the two namespaces. `compare_versions.py` reads both names with fallback.

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
| `ttm_eps` | Trailing-twelve-month EPS computed from quarterly EPS columns per the playbook month's anchor selection |
| `pe_current` | `close / ttm_eps` |

Legacy columns `q3_close` / `q3_date` / `q3_volume` (the `q3_` prefix was an internal SQL CTE artifact, **not** related to fiscal Q3) and `target_volume` / `ttm_eps_official` (step1 raw names) were removed because they sat alongside true quarterly columns (`ly_q3_eps`, etc.) and invited misreading. The canonical names above are emitted directly by step1; step2 no longer adds duplicate aliases.

## Rules

- **Date narration**: see [Date Convention](#date-convention-read-first). Any mention of "month M" in PRs / chat / log lines / code comments must carry the concrete `YYYY-MM-DD`. CLI args and directory layouts (`--year/--month`, `<Y>/<M>/`) keep the month-only form for terseness, but prose around them must expand.
- **Date terms**: `cutoff_date` belongs to target / cohort; `train_through_date` belongs to selection model. Don't write "model's cutoff_date" — say `train_through_date`.
- Do NOT add new SQL paths to deprecated tables (`income_statement`, `balance_sheet`, `cash_flow`, `quarterly_reports`).
- Do NOT commit generated `output/`, `models_selection/`, or csv/pkl artifacts unless asked.
- When adding XBRL account_codes, verify coverage across periods (some codes appear sparsely; check `data/processed/xbrl_codebook.csv`).
