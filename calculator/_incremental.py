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
  - fact tables that DO late-publish (monthly_revenue, *_xbrl) are not read
    by the calculators in this directory — they live in step1.

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
