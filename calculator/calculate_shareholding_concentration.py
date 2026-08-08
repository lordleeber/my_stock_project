import os
import sys

from sqlalchemy import text

sys.path.append(os.path.dirname(__file__))
from _incremental import (
    get_engine,
    get_last_processed_date,
    parse_force_full,
    table_exists,
)

from _error_report import abort_with_error

TABLE = "shareholding_concentration"

# WoW LAG computed inline. For incremental runs we need the **previous TDCC
# snapshot** per symbol to compute the new row's WoW delta — so the WHERE
# clause keeps `last_processed` itself (date >= :last), then we filter the
# output to date > :last before INSERT.
COMPUTE_SQL = """
WITH agg AS (
    SELECT
        date, symbol,
        SUM(CASE WHEN level BETWEEN 1 AND 8 THEN COALESCE(percentage, 0) ELSE 0 END) AS small_holder_ratio,
        SUM(CASE WHEN level BETWEEN 12 AND 15 THEN COALESCE(percentage, 0) ELSE 0 END) AS large_holder_ratio,
        SUM(CASE WHEN level BETWEEN 9 AND 11 THEN COALESCE(percentage, 0) ELSE 0 END) AS mid_holder_ratio,
        SUM(CASE WHEN level BETWEEN 1 AND 8 THEN COALESCE(holders, 0) ELSE 0 END) AS small_holder_count,
        SUM(CASE WHEN level BETWEEN 12 AND 15 THEN COALESCE(holders, 0) ELSE 0 END) AS large_holder_count
    FROM shareholding
    {where_clause}
    GROUP BY date, symbol
),
with_delta AS (
    SELECT
        date, symbol,
        large_holder_ratio, small_holder_ratio, mid_holder_ratio,
        (large_holder_ratio - small_holder_ratio) AS concentration_spread,
        large_holder_count, small_holder_count,
        large_holder_ratio - LAG(large_holder_ratio) OVER (PARTITION BY symbol ORDER BY date) AS large_holder_ratio_wow,
        small_holder_ratio - LAG(small_holder_ratio) OVER (PARTITION BY symbol ORDER BY date) AS small_holder_ratio_wow,
        mid_holder_ratio - LAG(mid_holder_ratio) OVER (PARTITION BY symbol ORDER BY date) AS mid_holder_ratio_wow,
        (large_holder_ratio - small_holder_ratio)
            - LAG(large_holder_ratio - small_holder_ratio) OVER (PARTITION BY symbol ORDER BY date)
            AS concentration_spread_wow
    FROM agg
)
SELECT
    date, symbol,
    ROUND(large_holder_ratio::numeric, 4) AS large_holder_ratio,
    ROUND(small_holder_ratio::numeric, 4) AS small_holder_ratio,
    ROUND(concentration_spread::numeric, 4) AS concentration_spread,
    large_holder_count, small_holder_count,
    ROUND(large_holder_ratio_wow::numeric, 4) AS large_holder_ratio_wow,
    ROUND(small_holder_ratio_wow::numeric, 4) AS small_holder_ratio_wow,
    ROUND(mid_holder_ratio_wow::numeric, 4) AS mid_holder_ratio_wow,
    ROUND(concentration_spread_wow::numeric, 4) AS concentration_spread_wow,
    ROUND(mid_holder_ratio::numeric, 4) AS mid_holder_ratio,
    'calculated_shareholding_concentration'::text AS pced_file,
    0::bigint AS pced_row,
    'x'::text AS pced_col
FROM with_delta
{output_filter};
"""


def _create_table_if_missing(conn):
    conn.execute(
        text(
            f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            large_holder_ratio DOUBLE PRECISION,
            small_holder_ratio DOUBLE PRECISION,
            concentration_spread DOUBLE PRECISION,
            large_holder_count BIGINT,
            small_holder_count BIGINT,
            large_holder_ratio_wow DOUBLE PRECISION,
            small_holder_ratio_wow DOUBLE PRECISION,
            mid_holder_ratio_wow DOUBLE PRECISION,
            concentration_spread_wow DOUBLE PRECISION,
            mid_holder_ratio DOUBLE PRECISION,
            pced_file TEXT,
            pced_row BIGINT,
            pced_col TEXT,
            PRIMARY KEY (date, symbol)
        )
        """
        )
    )
    conn.execute(
        text(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_symbol_date ON {TABLE} (symbol, date)"
        )
    )


def run(force_full=False):
    print("Starting Shareholding Concentration Calculator...")
    engine = get_engine()

    if not table_exists(engine, "shareholding"):
        print("shareholding table does not exist. Skip concentration calculation.")
        return

    if force_full:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        last_processed = None
        print("Force-full mode: dropped existing table, recomputing all history.")
    else:
        last_processed = get_last_processed_date(engine, TABLE)

    with engine.begin() as conn:
        _create_table_if_missing(conn)

    if last_processed is None:
        where_clause = ""
        output_filter = ""
        params = {}
        print("Computing full history...")
    else:
        # Include last_processed in the slice so LAG sees the previous snapshot,
        # then strip it from the INSERT.
        where_clause = "WHERE date >= :last"
        output_filter = "WHERE date > :last"
        params = {"last": last_processed}
        print(f"Incremental: appending rows with date > {last_processed}")

    sql = COMPUTE_SQL.format(where_clause=where_clause, output_filter=output_filter)
    cols = (
        "date, symbol, large_holder_ratio, small_holder_ratio, concentration_spread, "
        "large_holder_count, small_holder_count, large_holder_ratio_wow, "
        "small_holder_ratio_wow, mid_holder_ratio_wow, concentration_spread_wow, "
        "mid_holder_ratio, pced_file, pced_row, pced_col"
    )
    insert_sql = f"INSERT INTO {TABLE} ({cols}) {sql}"

    with engine.begin() as conn:
        if last_processed is not None:
            conn.execute(text(f"DELETE FROM {TABLE} WHERE date > :last"), params)
        result = conn.execute(text(insert_sql), params)
        inserted = result.rowcount

    with engine.connect() as conn:
        total_rows = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar()
        min_date, max_date = conn.execute(
            text(f"SELECT MIN(date), MAX(date) FROM {TABLE}")
        ).fetchone()

    print(
        f"{TABLE}: inserted {inserted} rows; total {total_rows} ({min_date} ~ {max_date})"
    )


def main():
    force_full = parse_force_full("Compute shareholding_concentration incrementally.")
    try:
        run(force_full=force_full)
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled {TABLE} calculator error: {e}", e)


if __name__ == "__main__":
    main()
