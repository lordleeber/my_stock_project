# Backtester TODO

## Scope
- Build a month-by-month walk-forward backtester for production strategy outputs.
- Use `strategies/strategy_blueprint.md` as the source of truth when conflicts exist.

## Input/Output Contract
- Input candidates path:
  - `strategies/output/<year>/<month>/results_candidates/trade_candidates_<release_yyyymmdd>.csv`
- Input strategy path:
  - `strategies/output/<year>/<month>/results_optimize/best_strategy.json`
- Output dir:
  - `backtester/output/<year>/<month>/`
- Output files:
  - `trades.csv`
  - `monthly_summary.csv`
  - `equity_curve.csv`
  - `summary.json`
- Baseline output files:
  - `trades_baseline.csv`
  - `monthly_summary_baseline.csv`
  - `equity_curve_baseline.csv`
  - `summary_baseline.json`

## Phase 1: Core Utilities
- [x] Add `backtester/utils.py`
- [x] Implement release-date rule (`05/08/11 -> 15`, others -> 10)
- [x] Implement candidate file resolver by release suffix (no legacy fallback)
- [x] Implement strict file checks (`FileNotFoundError` when missing)
- [x] Implement month calendar helpers (next month rollover)

## Phase 2: Data Loading Layer
- [x] Add `backtester/data_loader.py`
- [x] Read candidate CSV (`symbol,predict_target_price,close,entry_date` at minimum)
- [x] Read and parse `best_strategy.json` (`entry_rule`, `take_profit_rule`, `exit_rule`)
- [x] Validate `entry_date` exists and is parseable
- [x] Load quotes from DB `daily_quotes` for required symbol/date windows
- [x] Add defensive validation for duplicate rows / null critical prices

## Phase 3: Simulation Engine
- [x] Add `backtester/simulator.py`
- [ ] Entry logic:
  - [x] Use candidate `entry_date` as signal date
  - [x] Snap to next trading day as actual entry if needed
  - [x] Enforce look-ahead guard: `actual_entry_date >= signal_entry_date`
- [ ] Exit logic:
  - [x] Stop loss from `exit_rule.stop_loss_pct`
  - [x] Take profit from `take_profit_rule`
  - [x] Optional trailing stop when present
  - [x] Time stop from `exit_rule.max_hold_days` (trading-day based)
  - [x] Deterministic tie-break when stop/target hit same day (`prefer_stop_when_both`)
- [ ] Cost model:
  - [x] Apply commission/tax/slippage to return net PnL
- [ ] Result schema for each trade:
  - [x] symbol, signal_entry_date, actual_entry_date, entry_price
  - [x] exit_date, exit_price, exit_reason
  - [ ] gross_pnl, net_pnl, return_pct, holding_days
- [x] Position sizing: budget-based per stock (`--position-amount`, default `100000`)

## Phase 4: Monthly Runner
- [x] Add `backtester/run.py`
- [x] CLI: `--year --month`
- [x] Wire data loading + simulation + result writing
- [ ] Generate:
  - [x] `trades.csv`
  - [x] `monthly_summary.csv`
  - [x] `equity_curve.csv`
  - [x] `summary.json` (including violations/errors)
- [x] Fail-fast for required input missing (no old-path fallback)
- [x] Add `--position-amount`

## Phase 5: Batch Runner
- [x] Add `backtester/batch_run.py`
- [x] CLI: `--start_year --start_month --end_year --end_month`
- [x] Iterate months in order and run single-month pipeline
- [x] Skip month on missing inputs, continue next month, record skip reason
- [x] Generate batch-level summary report under `backtester/output/`
- [x] Add `--position-amount`

## Phase 5B: Baseline Runner
- [x] Add `backtester/run_baseline.py` for single-month baseline output
- [x] Add `backtester/batch_run_baseline.py` for month-range baseline output
- [x] Baseline rules implemented:
  - [x] Buy trigger: `price <= target_price * 0.9` (after signal entry date)
  - [x] Stop loss: `price <= entry_price * 0.9`
  - [x] Take profit: `price >= target_price`
  - [x] Final exit: last trading day close in quotes cache
- [x] Baseline uses budget-based position sizing (`--position-amount`, default `100000`)

## Phase 6: Validation & Tests
- [ ] Add unit tests for:
  - [ ] release-date calculation
  - [ ] candidate path resolver
  - [ ] max-hold trading-day end-date calculation
  - [ ] same-day stop/target tie-break
  - [ ] look-ahead violation detection
- [ ] Add integration test for one known month (`2023-08`) with fixed fixtures
- [ ] Verify core expectations:
  - [x] earliest entry aligns with candidate `entry_date` (manual validation done)
  - [x] end-date respects `max_hold_days` trading-day window (manual validation done)
  - [x] output schemas stable and reproducible (manual rerun validation done)

## Phase 7: Documentation
- [x] Update `backtester/CLAUDE.md` runbook after implementation
- [x] Document assumptions and edge-case handling
- [ ] Add troubleshooting section (missing inputs, missing quotes, DB connectivity)
- [x] Add summary tool: `backtester/summarize_range.py` (main + baseline)

## Acceptance Criteria
- [x] `venv/bin/python backtester/run.py --year 2023 --month 8` runs successfully when required inputs exist
- [x] `venv/bin/python backtester/batch_run.py ...` can process a month range without crashing on missing month inputs
- [x] Output files are generated with expected columns and valid dates
- [x] No look-ahead violation passes silently
- [x] Backtester behavior is aligned with `strategies/strategy_blueprint.md`
