"""Shared helpers for incremental-only calculators.

PIT-safe rule: never DROP+replace existing rows. Each calculator detects
MAX(date) on its output table and only computes rows with date > last_processed.

**Upstream assumption (intentionally unenforced)**: every consumer of these
helpers reads raw rows with `WHERE <raw_date> > :last`, so rows backfilled
*at or before* `last_processed` will NOT be picked up by incremental runs.
This is acceptable for the calculator vector because:
  - daily_quotes / institutional_investors / margin_* / shareholding are
    delete-before-insert at the importer layer and do not gain rows at
    historical dates after the fact;
  - monthly_revenue and income_statement/balance_sheet/cash_flow_xbrl — the
    late-publishing fact tables — are not read by any calculator here; they
    live in step1, which recomputes from scratch every run.

**The one exception**: calculate_valuation.py DOES read
quarterly_reports_xbrl, which late-publishes. It is safe under the daily
flow but not in general, because of how PIT alignment works there:
get_publish_date() maps a quarter to its *statutory deadline* (Q1 05-15 /
Q2 08-14 / Q3 11-14 / Q4 next 03-31) and merge_asof gives each price date
the latest report whose deadline is <= that date. So a newly published
report only changes rows at dates >= its deadline — in the daily flow those
are all > last_processed and get computed normally. Note the EPS side is
read unfiltered (no `> :last`); it is df_prices that bounds the window.

Two ways that breaks, both needing `--force-full` on valuation_daily:
  - **historical backfill** — quarters land whose deadline is already in the
    past, so the valuation_daily rows they should have changed are frozen.
    A backfill that adds *new symbols* is worse: those symbols get no
    historical rows at all, since incremental only emits date > last_processed.
    Happened 2026-08-17, when ~165 companies filing individual reports
    (REPORT_ID=A) were backfilled across 2020Q1~2026Q2.
  - **a quarter arriving after its own deadline** — scraped late, or filed
    late. Rows between the deadline and the arrival were computed without it
    and stay that way.
Restatements surface the same way; reconcile_ttm() in calculate_valuation.py
flags them (see calculator/CLAUDE.md).

pe_percentile_official is ranked *within each symbol's own history*
(groupby("symbol").expanding().rank), not cross-sectionally, so adding
symbols never disturbs the percentiles of existing ones.

If the upstream contract ever breaks (e.g. a backfill writes a row at an
already-processed date), use `--force-full` to rebuild the affected table.
The companion raw-table PIT leak (step1 fact-table queries missing
`publish_time <= cutoff` filter) is tracked separately in
strategies/EXPERIMENTS.md and is out of scope for this module.
"""

import argparse
import os

from sqlalchemy import create_engine, text


def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def get_engine():
    return create_engine(get_db_url())


def table_exists(engine, table_name):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t)"
            ),
            {"t": table_name},
        ).scalar()


def get_last_processed_date(engine, table_name):
    """Return MAX(date) (TEXT 'YYYY-MM-DD') from table, or None if missing/empty."""
    if not table_exists(engine, table_name):
        return None
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT MAX(date) FROM {table_name}")).scalar()


def parse_force_full(description):
    """Standard CLI parser used by every calculator's __main__."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Drop output table and recompute full history. Use after schema "
        "changes or bug fixes — disables PIT-safety guarantees for prior rows.",
    )
    args = parser.parse_args()
    return args.force_full
