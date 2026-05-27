import os
import sys
import traceback

from sqlalchemy import text

sys.path.append(os.path.dirname(__file__))
from _incremental import get_engine, get_last_processed_date, parse_force_full

ERROR_LOG = "/error_calculator.log"
TABLE = "short_interest_analysis"


def abort_with_error(message, exception=None):
    with open(ERROR_LOG, "w") as f:
        f.write("# Calculator 錯誤報告\n\n")
        f.write(f"## 錯誤訊息\n\n{message}\n\n")
        if exception is not None:
            f.write(f"## Traceback\n\n```\n{traceback.format_exc()}\n```\n")
    print(f"\n❌ {message}")
    print(f"錯誤已寫入 {ERROR_LOG}")
    raise SystemExit(1)


# Single-row derivation: every metric in short_interest_analysis comes from the
# same-day margin_sbl row (no LAG / no rolling). Incremental = pure date filter.
SELECT_AND_INSERT_SQL = """
INSERT INTO {table} (
    date, market, symbol, name,
    sbl_balance, sbl_balance_wow, sbl_balance_wow_pct,
    sbl_sell, sbl_repay, sbl_sell_repay_ratio,
    margin_short_balance, margin_short_balance_wow, margin_short_balance_wow_pct,
    short_pressure_score, pced_file, pced_row, pced_col
)
WITH base AS (
    SELECT
        date, market, symbol,
        MAX(name) AS name,
        SUM(COALESCE(sbl_balance, 0)) AS sbl_balance,
        SUM(COALESCE(sbl_prev_balance, 0)) AS sbl_prev_balance,
        SUM(COALESCE(sbl_sell, 0)) AS sbl_sell,
        SUM(COALESCE(sbl_repay, 0)) AS sbl_repay,
        SUM(COALESCE(margin_short_balance, 0)) AS margin_short_balance,
        SUM(COALESCE(margin_short_prev_balance, 0)) AS margin_short_prev_balance
    FROM margin_sbl
    {where_clause}
    GROUP BY date, market, symbol
),
with_delta AS (
    SELECT
        date, market, symbol, name,
        sbl_balance,
        sbl_balance - sbl_prev_balance AS sbl_balance_wow,
        CASE
            WHEN sbl_prev_balance > 0 THEN (sbl_balance - sbl_prev_balance) / sbl_prev_balance * 100
            ELSE NULL
        END AS sbl_balance_wow_pct,
        sbl_sell, sbl_repay,
        CASE WHEN sbl_repay > 0 THEN sbl_sell / sbl_repay ELSE NULL END AS sbl_sell_repay_ratio,
        margin_short_balance,
        margin_short_balance - margin_short_prev_balance AS margin_short_balance_wow,
        CASE
            WHEN margin_short_prev_balance > 0
            THEN (margin_short_balance - margin_short_prev_balance) / margin_short_prev_balance * 100
            ELSE NULL
        END AS margin_short_balance_wow_pct
    FROM base
)
SELECT
    date, market, symbol, name,
    sbl_balance,
    ROUND(sbl_balance_wow::numeric, 4),
    ROUND(sbl_balance_wow_pct::numeric, 4),
    sbl_sell, sbl_repay,
    ROUND(sbl_sell_repay_ratio::numeric, 4),
    margin_short_balance,
    ROUND(margin_short_balance_wow::numeric, 4),
    ROUND(margin_short_balance_wow_pct::numeric, 4),
    ROUND(
        (
            COALESCE(sbl_balance_wow_pct, 0) * 0.4
            + COALESCE(margin_short_balance_wow_pct, 0) * 0.4
            + (COALESCE(sbl_sell_repay_ratio, 1) - 1) * 100 * 0.2
        )::numeric, 4
    ) AS short_pressure_score,
    'calculated_short_interest_analysis'::text, 0::bigint, 'x'::text
FROM with_delta;
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
            sbl_balance DOUBLE PRECISION,
            sbl_balance_wow DOUBLE PRECISION,
            sbl_balance_wow_pct DOUBLE PRECISION,
            sbl_sell DOUBLE PRECISION,
            sbl_repay DOUBLE PRECISION,
            sbl_sell_repay_ratio DOUBLE PRECISION,
            margin_short_balance DOUBLE PRECISION,
            margin_short_balance_wow DOUBLE PRECISION,
            margin_short_balance_wow_pct DOUBLE PRECISION,
            short_pressure_score DOUBLE PRECISION,
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
    print("Starting Short Interest Analysis Calculator...")
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
        # DELETE+INSERT in same txn → idempotent for re-run of same range
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
    force_full = parse_force_full("Compute short_interest_analysis incrementally.")
    try:
        run(force_full=force_full)
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled {TABLE} calculator error: {e}", e)


if __name__ == "__main__":
    main()
