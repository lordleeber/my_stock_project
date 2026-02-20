import os
import sys
import traceback

from sqlalchemy import create_engine, text


ERROR_LOG = "/error_calculator.log"


def abort_with_error(message, exception=None):
    with open(ERROR_LOG, "w") as f:
        f.write("# Calculator 錯誤報告\n\n")
        f.write(f"## 錯誤訊息\n\n{message}\n\n")
        if exception is not None:
            f.write(f"## Traceback\n\n```\n{traceback.format_exc()}\n```\n")
    print(f"\n❌ {message}")
    print(f"錯誤已寫入 {ERROR_LOG}")
    raise SystemExit(1)


def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def run():
    print("Starting Shareholding Concentration Calculator...")
    engine = create_engine(get_db_url())

    with engine.connect() as conn:
        has_shareholding = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='shareholding')"
            )
        ).scalar()

    if not has_shareholding:
        print("shareholding table does not exist. Skip concentration calculation.")
        return

    create_sql = text(
        """
        DROP TABLE IF EXISTS shareholding_concentration;

        CREATE TABLE shareholding_concentration AS
        WITH agg AS (
            SELECT
                date,
                symbol,
                SUM(CASE WHEN level BETWEEN 1 AND 8 THEN COALESCE(percentage, 0) ELSE 0 END) AS small_holder_ratio,
                SUM(CASE WHEN level BETWEEN 12 AND 15 THEN COALESCE(percentage, 0) ELSE 0 END) AS large_holder_ratio,
                SUM(CASE WHEN level BETWEEN 1 AND 8 THEN COALESCE(holders, 0) ELSE 0 END) AS small_holder_count,
                SUM(CASE WHEN level BETWEEN 12 AND 15 THEN COALESCE(holders, 0) ELSE 0 END) AS large_holder_count
            FROM shareholding
            GROUP BY date, symbol
        ),
        with_delta AS (
            SELECT
                date,
                symbol,
                large_holder_ratio,
                small_holder_ratio,
                (large_holder_ratio - small_holder_ratio) AS concentration_spread,
                large_holder_count,
                small_holder_count,
                large_holder_ratio - LAG(large_holder_ratio) OVER (PARTITION BY symbol ORDER BY date) AS large_holder_ratio_wow,
                small_holder_ratio - LAG(small_holder_ratio) OVER (PARTITION BY symbol ORDER BY date) AS small_holder_ratio_wow,
                (large_holder_ratio - small_holder_ratio) - LAG(large_holder_ratio - small_holder_ratio) OVER (PARTITION BY symbol ORDER BY date) AS concentration_spread_wow
            FROM agg
        )
        SELECT
            date,
            symbol,
            ROUND(large_holder_ratio::numeric, 4) AS large_holder_ratio,
            ROUND(small_holder_ratio::numeric, 4) AS small_holder_ratio,
            ROUND(concentration_spread::numeric, 4) AS concentration_spread,
            large_holder_count,
            small_holder_count,
            ROUND(large_holder_ratio_wow::numeric, 4) AS large_holder_ratio_wow,
            ROUND(small_holder_ratio_wow::numeric, 4) AS small_holder_ratio_wow,
            ROUND(concentration_spread_wow::numeric, 4) AS concentration_spread_wow,
            'calculated_shareholding_concentration'::text AS pced_file,
            0::bigint AS pced_row,
            'x'::text AS pced_col
        FROM with_delta;
        """
    )

    with engine.begin() as conn:
        conn.execute(create_sql)
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_shareholding_concentration_symbol_date "
                "ON shareholding_concentration (symbol, date)"
            )
        )

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM shareholding_concentration")).scalar()
        min_date, max_date = conn.execute(
            text("SELECT MIN(date), MAX(date) FROM shareholding_concentration")
        ).fetchone()

    print(
        "shareholding_concentration rebuilt successfully: "
        f"{total_rows} rows ({min_date} ~ {max_date})"
    )


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled shareholding_concentration calculator error: {e}", e)


if __name__ == "__main__":
    main()
