import os
import sys

from sqlalchemy import text

sys.path.append(os.path.dirname(__file__))
from _incremental import get_engine, get_last_processed_date, parse_force_full

from _error_report import abort_with_error

TABLE = "margin_pressure_analysis"

# Single-row derivation: all margin_pressure_analysis metrics come from
# same-day margin_trading row (uses *_prev_balance from source, no LAG).
SELECT_AND_INSERT_SQL = """
INSERT INTO {table} (
    date, market, symbol, name,
    margin_long_balance, margin_long_limit, margin_usage_ratio,
    margin_long_balance_wow, margin_long_balance_wow_pct,
    margin_short_balance, margin_short_limit, short_usage_ratio,
    margin_short_balance_wow, margin_short_balance_wow_pct,
    short_cover_pressure, margin_pressure_score,
    pced_file, pced_row, pced_col
)
WITH base AS (
    SELECT
        date, market, symbol,
        MAX(name) AS name,
        SUM(COALESCE(margin_long_prev_balance, 0)) AS margin_long_prev_balance,
        SUM(COALESCE(margin_long_balance, 0)) AS margin_long_balance,
        SUM(COALESCE(margin_long_limit, 0)) AS margin_long_limit,
        SUM(COALESCE(margin_short_prev_balance, 0)) AS margin_short_prev_balance,
        SUM(COALESCE(margin_short_balance, 0)) AS margin_short_balance,
        SUM(COALESCE(margin_short_limit, 0)) AS margin_short_limit,
        SUM(COALESCE(margin_short_buy, 0)) AS margin_short_buy,
        SUM(COALESCE(margin_short_cash_repay, 0)) AS margin_short_cash_repay
    FROM margin_trading
    {where_clause}
    GROUP BY date, market, symbol
)
SELECT
    date, market, symbol, name,
    margin_long_balance, margin_long_limit,
    ROUND(CASE WHEN margin_long_limit > 0
              THEN margin_long_balance / margin_long_limit * 100 ELSE NULL END::numeric, 4),
    ROUND((margin_long_balance - margin_long_prev_balance)::numeric, 4),
    ROUND(CASE WHEN margin_long_prev_balance > 0
              THEN (margin_long_balance - margin_long_prev_balance) / margin_long_prev_balance * 100
              ELSE NULL END::numeric, 4),
    margin_short_balance, margin_short_limit,
    ROUND(CASE WHEN margin_short_limit > 0
              THEN margin_short_balance / margin_short_limit * 100 ELSE NULL END::numeric, 4),
    ROUND((margin_short_balance - margin_short_prev_balance)::numeric, 4),
    ROUND(CASE WHEN margin_short_prev_balance > 0
              THEN (margin_short_balance - margin_short_prev_balance) / margin_short_prev_balance * 100
              ELSE NULL END::numeric, 4),
    ROUND(CASE WHEN margin_short_prev_balance > 0
              THEN (margin_short_buy + margin_short_cash_repay) / margin_short_prev_balance * 100
              ELSE NULL END::numeric, 4),
    ROUND(
        (
            COALESCE(CASE WHEN margin_long_limit > 0
                          THEN margin_long_balance / margin_long_limit * 100 ELSE NULL END, 0) * 0.45
            + COALESCE(CASE WHEN margin_short_limit > 0
                            THEN margin_short_balance / margin_short_limit * 100 ELSE NULL END, 0) * 0.30
            + COALESCE(CASE WHEN margin_short_prev_balance > 0
                            THEN (margin_short_buy + margin_short_cash_repay) / margin_short_prev_balance * 100
                            ELSE NULL END, 0) * 0.25
        )::numeric, 4
    ),
    'calculated_margin_pressure_analysis'::text, 0::bigint, 'x'::text
FROM base;
"""


def _create_table_if_missing(conn):
    conn.execute(
        text(
            f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            date TEXT NOT NULL,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT,
            margin_long_balance DOUBLE PRECISION,
            margin_long_limit DOUBLE PRECISION,
            margin_usage_ratio DOUBLE PRECISION,
            margin_long_balance_wow DOUBLE PRECISION,
            margin_long_balance_wow_pct DOUBLE PRECISION,
            margin_short_balance DOUBLE PRECISION,
            margin_short_limit DOUBLE PRECISION,
            short_usage_ratio DOUBLE PRECISION,
            margin_short_balance_wow DOUBLE PRECISION,
            margin_short_balance_wow_pct DOUBLE PRECISION,
            short_cover_pressure DOUBLE PRECISION,
            margin_pressure_score DOUBLE PRECISION,
            pced_file TEXT,
            pced_row BIGINT,
            pced_col TEXT,
            PRIMARY KEY (date, market, symbol)
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
    print("Starting Margin Pressure Analysis Calculator...")
    engine = get_engine()

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
        params = {}
        print("Computing full history...")
    else:
        where_clause = "WHERE date > :last"
        params = {"last": last_processed}
        print(f"Incremental: appending rows with date > {last_processed}")

    sql = SELECT_AND_INSERT_SQL.format(table=TABLE, where_clause=where_clause)

    with engine.begin() as conn:
        if last_processed is not None:
            conn.execute(text(f"DELETE FROM {TABLE} WHERE date > :last"), params)
        result = conn.execute(text(sql), params)
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
    force_full = parse_force_full("Compute margin_pressure_analysis incrementally.")
    try:
        run(force_full=force_full)
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled {TABLE} calculator error: {e}", e)


if __name__ == "__main__":
    main()
