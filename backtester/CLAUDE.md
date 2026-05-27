# backtester AI Guide

## Scope
- Work only inside `backtester/`.
- Responsibility: rolling walk-forward portfolio backtester + summary tooling.

## Commands

```bash
# Roll forward over a playbook-date range; outputs in backtester/output/rolling/
# --end-date optional: if omitted, auto-detect latest playbook date with
# candidates_scored.csv AND DB daily_quotes coverage for entry_date.
venv/bin/python3 backtester/run_rolling.py \
  --start-date 2022-07-11 \
  --top-n 10 --position-amount 100000

# Explicit end (override auto-detect)
venv/bin/python3 backtester/run_rolling.py \
  --start-date 2022-07-11 \
  --end-date 2026-04-11 \
  --top-n 10 --position-amount 100000

# Print aggregate summary from latest rolling_trades.csv
venv/bin/python3 backtester/summarize_range.py
```

`--start-date` / `--end-date` 都是 canonical playbook run date（cutoff +1：5/8/11 月 = 16 號，其餘月份 = 11 號）。

## End-date auto-detection

When `--end-date` is omitted, `run_rolling.py` scans `models_selection/<YYYY-MM-DD>/`
(newest first) and picks the latest date where:

1. `candidates_scored.csv` exists, AND
2. its `entry_date` has at least one matching record in `daily_quotes` (i.e.
   `daily_quotes.date >= entry_date` returns a row).

Rule (2) catches the case where `candidates_scored.csv` was published for a
playbook whose rotation date hasn't yet been quoted in the DB (e.g.
`entry_date=2026-05-16` while DB max date is `2026-05-15`) — those would
otherwise produce `entries_failed_no_quote=10` and pollute the run.
The resolved end is printed to stdout at start (`[auto-detect] end = YYYY-MM-DD`).

## Skipped Months (Feb / Mar)

Backtester does **not** open new positions for playbook_date months `02` and `03`.

Reason: `strategies/step1_prepare_data.py` derives `anchor_q` via
`build_quarter_context`, which for Feb/Mar cohorts maps to the previous
year's Q4. But Q4's official publish deadline is Mar 31 of the following
year — strictly **after** the Feb (02-10) and Mar (03-10) cutoff dates.
So all Feb/Mar candidate features are computed against data that wasn't
yet published as of the cohort's cutoff (PIT leak). Until
`build_quarter_context` is rewritten to use a publish-aware anchor, the
honest move is to refuse to backtest these cohorts.

Behaviour during a skipped iteration:
- **exit** runs normally: previous cohort is sold at `exit_date` (= the
  trading day before the skipped playbook's `entry_date`); its
  `realized_net_pnl` is recorded on the skipped row.
- **entry** is suppressed: `entries=0`, `entries_failed_no_quote=0`,
  `holdings_count` drops to 0 after exit.
- Next non-skip iteration (typically April) starts with an empty portfolio
  and opens its full cohort.

Result: yearly cohort count drops from 12 → 10 (Jan and Apr still run;
Feb and Mar appear in `rolling_monthly.csv` but with `entries=0` and zero
`portfolio_capital_deployed`). step1/step2/step5 still generate Feb/Mar
artifacts — they're computed but never consumed by `run_rolling.py`.

## ⚠️ Monthly Sharpe — Always Use the 38-Basis

Because Feb/Mar skip adds **no-PnL artifact rows** to `rolling_monthly.csv`,
any monthly Sharpe / win-rate computed against the raw 47 rows silently
deflates. The canonical convention is to filter on `cohort_year.notna()`
(only rows where an actual cohort was settled), and use
`top_n × position_amount` as the return denominator (not
`portfolio_capital_deployed`, which is 0 on Feb rows that just exited).

The 9 artifact rows per 4-year run that must be excluded:

| Row type | Why excluded |
|---|---|
| First iteration (e.g., 2022-07-11) | No prior cohort to exit, `realized_net_pnl=0` |
| Mar rows (4) | No exit (already empty from Feb skip) + no entry → `0/0` |
| Apr rows (4) | Re-entry only, no exit (portfolio was empty) → entry-only |

`run_rolling.py` writes the 38-basis numbers into
`rolling_summary.json["monthly_stats_38_basis"]` (single source of truth).
`summarize_range.py` reads them back. Don't recompute from
`rolling_monthly.csv` ad-hoc — you'll trip over the artifact rows.

Annualization factor = √(actual_cohorts / years_span), typically √10 ≈ 3.16
post-skip (vs the textbook √12 from pre-skip days). It's stored explicitly
in `monthly_stats_38_basis["annualization_factor"]` to keep prior-period
comparisons honest.

When comparing against pre-Feb/Mar-skip baselines (which used the old
47-basis ann ×√12), the apples-to-apples metric is **per-cohort Sharpe
ann ×√10**, not 47-basis ann ×√12. A 5-cohort drop in the denominator
(47→38) on the same strategy gives a ~10% lower "ann ×√12" number for
purely arithmetic reasons.

## Output Files (`backtester/output/rolling/`)

| File | Granularity |
|---|---|
| `rolling_summary.json` | Aggregate stats over the whole run |
| `rolling_monthly.csv` | One row per **loop iteration** (rotation event) |
| `rolling_trades.csv` | One row per **trade** (entry + matching exit) |

## ⚠️ `rolling_monthly.csv` Column Semantics

This is the trap: each row's `playbook_date` / `year` / `month` is **the rotation event's playbook**, but `realized_net_pnl` belongs to the **previous cohort** (the one being sold). Two time axes in one row.

| Column | What it points at |
|---|---|
| `playbook_date` | This iteration's playbook_date (YYYY-MM-DD) — the rotation event |
| `year`, `month` | Year/month derived from `playbook_date` (cohort label convenience) |
| `entry_date` | New cohort's entry date (this iteration's buys) |
| `exit_date` | Last trading day before `entry_date` — when the previous cohort is sold |
| `cohort_year`, `cohort_month` | **The cohort being settled** — the one whose PnL appears in `realized_net_pnl` (= previous playbook calendar-wise; NaN in the first iteration when portfolio was empty) |
| `cohort_entry_date` | When the settled cohort originally entered (lookup-friendly) |
| `regime` | Bull / Sideways / Bear detected at `entry_date` (observational only; does NOT affect entries since 226b6be) |
| `holdings_count` | Portfolio size AFTER rotation (= new cohort size) |
| `exits` | How many positions were sold this iteration |
| `entries` | How many new positions were opened |
| `entries_failed_no_quote` | New picks dropped because no open price was available |
| `realized_net_pnl` | PnL of the cohort named in `cohort_year/cohort_month` — sold this iteration |
| `portfolio_capital_deployed` | Sum of `entry_price × shares` across current portfolio |

### Concrete example
Row `playbook_date=2026-04-11, year=2026, month=04, entry_date=2026-04-13, cohort_year=2026, cohort_month=03, cohort_entry_date=2026-03-11, realized_net_pnl=335596.49`:
- The **March cohort** entered 2026-03-11 and was sold at 2026-04-10 open for net +335,596.
- The April cohort entered 2026-04-13; its PnL will only appear later in the row for `playbook_date=2026-05-16` (when it's sold at 2026-05-15 open).

### Looking up a cohort's PnL
`df[(df.cohort_year == 2026) & (df.cohort_month == "03")]['realized_net_pnl']`

### Why this is the trap
A naive `groupby('playbook_date').sum('realized_net_pnl')` will attribute March's PnL to April — wrong. Always group by `cohort_year/cohort_month` when summarizing per-cohort performance.

## Still-Open Positions
The final iteration's new cohort is left in the portfolio without being settled. `rolling_summary.json` reports `still_open_count` and `rolling_trades.csv` has rows with `exit_date=NaN`. To realize them, extend `--end-date` by one playbook (which requires the next playbook's `candidates_scored.csv` to exist).

## Per-Trade File (`rolling_trades.csv`)
Each row is one round-trip trade. Columns include `entry_date`, `exit_date`, `entry_price`, `exit_price`, `shares`, `gross_pnl`, `cost`, `net_pnl`, `exit_reason`. This file is unambiguous — each row maps to a single cohort.

## Rules
- Do NOT commit `output/rolling/*.csv` or `*.json` (regenerable artifacts).
- When changing the rotation logic, update both `rolling_monthly.csv` schema and this doc.
- Walk-forward rule: target playbook M uses the latest selection model with `train_through_playbook_date < M`. Run `strategies/step5_score_and_publish.py --date M` for playbook M before backtesting through M.
