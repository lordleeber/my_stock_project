# Fundamental Strategy Notes for AI Assistants

This document is a practical reference for maintaining `strategy/fundamental/*` scripts.

## Scope
- `flagship_screener.py`
- `valuation_screener.py`
- `price_range_analyzer.py`
- `screener_base.py`

## General Rules
- Always avoid look-ahead bias in historical runs.
- Restrict data windows to what was available on the decision date.
- Prefer robust filtering over optimistic fallback estimates.
- Drop records that cannot produce valid TTM EPS.

## Quarter Effective Dates
Use market-specific report availability dates.

### SII
- Q1 (Jan-Mar): `YYYY-05-15`
- Q2 (Apr-Jun): `YYYY-08-14`
- Q3 (Jul-Sep): `YYYY-11-14`
- Q4 (Oct-Dec): `(YYYY+1)-03-31`

### OTC
- Q1: 20th business day of June (`YYYY-06`)
- Q2: 20th business day of September (`YYYY-09`)
- Q3: 20th business day of December (`YYYY-12`)
- Q4: 20th business day of April (`YYYY+1-04`)

## Input Constraints
- Earliest allowed quarter: `2020Q4`.
- `--quarter` is required in both screeners.
- `--market` (or legacy alias `--martket`) is required and must be one of `{sii, otc}`.

## Shared Base Utilities (`screener_base.py`)
- `calculate_ttm_eps(df_income)`
- `build_ttm_eps_for_quarter(df_income_all, quarter)`
- `fetch_pe_ratio_for_date(fetch_dataframe_func, target_date, limit=5000)`

Notes:
- Do not use row-index-as-symbol fallback.
- If a stock lacks enough quarterly rows for full TTM, exclude it.
- PE data should come from `/raw/pe-ratio`.

## `flagship_screener.py`
Current behavior:
- Uses TTM EPS instead of single-quarter annualization.
- Enforces quarter and market constraints above.
- Uses `/raw/pe-ratio` for PE values.
- `predict_price` has been removed from output and scoring path.

Output naming:
- `fundamental_report_<quarter>_<market>.csv`

## `valuation_screener.py`
Current behavior:
- Enforces quarter and market constraints above.
- Uses shared TTM EPS logic from `screener_base.py`.
- Does not use fallback `eps * 4`.
- Stocks without complete TTM inputs are dropped.

Output naming:
- `undervalued_picks_<quarter>_<market>.csv`

## `price_range_analyzer.py`
CLI requirements:
- `--report-path` (required)
- `--market/--martket {sii,otc}` (required)
- Either:
  - `--start-date` and `--end-date`, or
  - `--start-quarter` and `--end-quarter`

Output columns:
- `symbol,name,industry,start_date,start_price,end_date,end_price,period_high,period_low,max_upside_pct,max_drawdown_pct,total_score`

Output naming:
- `price_analysis_ref_<report_stem>_<start>_<end>_<market>.csv`

Data-fetch reliability fix:
- Old issue: wide date-range query + API `limit` could truncate rows and produce invalid highs/lows.
- Current approach: fetch `/raw/daily-quotes` by symbol (from report) across the target period first.
- Fallback to wide-range mode only when symbol-mode returns no data.
- Use `limit=5000` for stability.

## Maintenance Checklist
Before committing changes:
- Validate required CLI arguments still fail fast when missing.
- Verify quarter-date mapping for both markets.
- Confirm no look-ahead data leakage.
- Confirm PE source remains `/raw/pe-ratio`.
- Confirm generated filenames include quarter/date and market suffixes.
