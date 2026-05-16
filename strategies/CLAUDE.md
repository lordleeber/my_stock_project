# strategies AI Guide

## Scope
- Work only inside `strategies/`.
- Responsibility: monthly candidate dataset + LGBMRanker selection model training/scoring.

## Pipeline Layout

| Step | Script | Output |
|---|---|---|
| 1 | `step1_prepare_data.py --year Y --month M` | `output/<Y>/<M>/dataset_strategy.csv` (40 cols, after ttm/volume filter) |
| 2 | `step2_finalize_strategy.py --year Y --month M` | enrich `dataset_strategy.csv` with technical/revenue/EPS-prediction features (76 cols); write `trade_candidates.csv` |
| 3 | `step3_analyze_feature_returns.py` | `feature_return_analysis.csv` (fwd_return ground truth) |
| 4 | `step4_train_selection_model.py --cutoff-year Y --cutoff-month M` | `models_selection/<Y>/<M>/selection_model.pkl` + feature_importance + latest.json |
| 5 | `step5_score_and_publish.py --year Y --month M` | `models_selection/<Y>/<M>/candidates_scored.csv` (final picks by `ml_rank`) |

Batch variants (`stepN_batch_*.py`) loop the same logic over month ranges.

## Data Sources (DB tables)

Step1 reads from:

| Table | Purpose | Filter |
|---|---|---|
| `quarterly_reports_xbrl` | anchor & previous quarter wide-format facts (revenue_q, net_income_q, pretax_income_q, non_op_income_q, capital, eps_q) | `date IN (anchor_q, prev_q, ...)` AND `period_type='quarter'` |
| `balance_sheet_xbrl` | total_assets (1XXX), total_liabilities (2XXX), total_equity (3XXX), retained_earnings (3300) | `date=anchor_q` AND `period_type='as_of'` AND `account_code IN (...)` |
| `cash_flow_xbrl` | operating cash flow (AAAA, accumulated) — converted to single-quarter | `date IN (anchor_q, prev_q)` AND `period_type='accumulated'` AND `account_code='AAAA'` |
| `stock_info` | name + industry + canonical market | LEFT JOIN, fallback to `quarterly_reports_xbrl.market` |
| `monthly_revenue` | monthly revenue features | `date IN mctx.mr_dates` |
| `daily_quotes` | latest close/volume on or before cutoff_date | `date <= cutoff_date` AND `market=...` |
| `valuation_daily` | roe_official, pe_percentile_official (PIT-aligned) | latest per symbol where `date <= end_date` |
| chip/sentiment tables | `foreign_holding`, `trust_holding`, `dealer_holding`, `large_holders`, `margin_sbl`, `margin_pressure_analysis`, `short_interest_analysis` | per-feature SQL |

> Old tables `income_statement` / `balance_sheet` / `cash_flow` are deprecated. Step1 no longer touches them.

## Anchor Quarter Cash-Flow Conversion

`cash_flow_xbrl` only stores `period_type='accumulated'` (year-to-date values). For the anchor quarter's single-quarter OCF:

```
anchor_ocf = (anchor_q acc) − (prev_q acc)        if anchor_q is Q2/Q3/Q4
           = anchor_q acc                         if anchor_q is Q1 (no Y-T-D before Q1)
```

The SQL uses `CASE WHEN RIGHT(anchor_q, 2) = 'Q1' THEN ... ELSE ... END` to handle the Q1 special case. `prev_q` for a Q1 anchor is the prior year's Q4, whose accumulated value is the full-year — subtracting it would yield garbage.

## Market Label Inconsistency

About 1–2% of symbols have different market labels across tables (e.g., `quarterly_reports_xbrl.market='sii'` but `stock_info.market='otc'`, or symbol missing from `stock_info` altogether). Step1's filter uses `COALESCE(stock_info.market, quarterly_reports_xbrl.market) = '{market}'` so each symbol appears in exactly one market run. The downstream `pd.concat` of sii+otc produces a single deduplicated universe.

## Filters in Step1

| Filter | Threshold |
|---|---|
| TTM EPS proxy | `ly_target_eps + prev_eps + anchor_eps ≥ 2.0` |
| Min average volume | `volume_lots ≥ 500` |

Hard filter values are constants in `step1_prepare_data.py` near the top — change with care; backtester reproducibility depends on them.

## Step2 Adds

- Technical: MA5/10/20/60/240, RSI6/12, KD, MACD, BB position, volume ratios
- Revenue momentum: YoY 1m / 3m avg / cum / mom / accel / positive streak
- EPS prediction merge: `pred_lgb_delta`, `predict_target_eps`, `predict_target_price`, `pred_upside_pct` from `models_eps/<Y>/<M>/predictions_results.csv`
- `entry_date` = the cutoff_date's next trading day

`trade_candidates.csv` filters `dataset_strategy.csv` by `pred_upside_pct > 0` and sorts by upside.

## Walk-Forward Selection Model

- Models stored at `models_selection/<cutoff_year>/<cutoff_month>/`
- Scoring month M (step5) picks the latest model with cutoff < M
- Training month M-1 model requires step3 fwd_return reaching M-1, which requires step1+2 for month M (entry_date) to be done first

See [`MONTHLY_PLAYBOOK.md`](../MONTHLY_PLAYBOOK.md) for the strict ordering rule.

## ⚠️ `models_selection/<Y>/<M>/` Directory Has Dual Meaning

Same directory, two files with different temporal labels:

| File | `M` interpretation |
|---|---|
| `selection_model.pkl` | M is **cutoff** — training used data up to cohort M's fwd_return |
| `candidates_scored.csv` | M is **target** — scored by a model with cutoff **< M** (walk-forward) |

Example: `models_selection/2026/04/candidates_scored.csv` lists April candidates scored by `models_selection/2026/03/selection_model.pkl` (or earlier). The April model in the same directory was trained later and is used for **May** candidates.

To remove ambiguity, step5 writes a `scored_by_model_cutoff` column into `candidates_scored.csv` (value like `"2026/03"`) so the model source is always self-evident from the file alone.

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

- Do NOT add new SQL paths to deprecated tables (`income_statement`, `balance_sheet`, `cash_flow`, `quarterly_reports`).
- Do NOT commit generated `output/`, `models_selection/`, or csv/pkl artifacts unless asked.
- When adding XBRL account_codes, verify coverage across periods (some codes appear sparsely; check `data/processed/xbrl_codebook.csv`).
