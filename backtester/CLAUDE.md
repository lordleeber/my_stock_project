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
