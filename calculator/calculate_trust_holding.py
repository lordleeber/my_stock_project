import os
import sys

from sqlalchemy import text

sys.path.append(os.path.dirname(__file__))
from _incremental import get_engine, get_last_processed_date, parse_force_full

from _error_report import make_abort

ERROR_LOG = "/error_calculator.log"
TABLE = "trust_holding"


abort_with_error = make_abort(ERROR_LOG)


# Cumulative SUM: same pattern as dealer_holding — see comment there.
INSERT_SQL = """
INSERT INTO {table} (
    date, market, symbol, name, issued_shares,
    trust_held_shares, trust_held_ratio,
    pced_file, pced_row, pced_col
)
WITH last_state AS (
    SELECT DISTINCT ON (market, symbol)
        market, symbol, trust_held_shares AS last_shares
    FROM {table}
    ORDER BY market, symbol, date DESC
),
new_daily AS (
    SELECT
        ii.date, ii.market, ii.symbol,
        MAX(ii.name) AS name,
        SUM(COALESCE(ii.trust_net, 0)) AS trust_net
    FROM institutional_investors ii
    {where_clause}
    GROUP BY ii.date, ii.market, ii.symbol
),
new_cum AS (
    SELECT
        nd.date, nd.market, nd.symbol, nd.name,
        COALESCE(ls.last_shares, 0) + SUM(nd.trust_net) OVER (
            PARTITION BY nd.market, nd.symbol
            ORDER BY nd.date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS trust_held_shares
    FROM new_daily nd
    LEFT JOIN last_state ls
        ON nd.market = ls.market AND nd.symbol = ls.symbol
)
SELECT
    nc.date, nc.market, nc.symbol,
    COALESCE(fh.name, nc.name) AS name,
    fh.issued_shares,
    nc.trust_held_shares,
    CASE WHEN fh.issued_shares > 0
         THEN ROUND((nc.trust_held_shares / fh.issued_shares * 100)::numeric, 4)
         ELSE NULL
    END AS trust_held_ratio,
    'calculated_trust_holding'::text, 0::bigint, 'x'::text
FROM new_cum nc
LEFT JOIN foreign_holding fh
    ON nc.date = fh.date AND nc.market = fh.market AND nc.symbol = fh.symbol;
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
            issued_shares DOUBLE PRECISION,
            trust_held_shares DOUBLE PRECISION,
            trust_held_ratio DOUBLE PRECISION,
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
    print("Starting Trust Holding Calculator...")
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
        where_clause = "WHERE ii.date > :last"
        params = {"last": last_processed}
        print(f"Incremental: appending rows with date > {last_processed}")

    sql = INSERT_SQL.format(table=TABLE, where_clause=where_clause)

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
    force_full = parse_force_full("Compute trust_holding incrementally.")
    try:
        run(force_full=force_full)
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled {TABLE} calculator error: {e}", e)


if __name__ == "__main__":
    main()
