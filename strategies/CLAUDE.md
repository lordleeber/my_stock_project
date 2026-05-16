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

## Rules

- Do NOT add new SQL paths to deprecated tables (`income_statement`, `balance_sheet`, `cash_flow`, `quarterly_reports`).
- Do NOT commit generated `output/`, `models_selection/`, or csv/pkl artifacts unless asked.
- When adding XBRL account_codes, verify coverage across periods (some codes appear sparsely; check `data/processed/xbrl_codebook.csv`).
