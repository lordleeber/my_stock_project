import os
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
    print("Starting Trust Holding Calculator...")
    engine = create_engine(get_db_url())

    create_sql = text(
        """
        DROP TABLE IF EXISTS trust_holding;

        CREATE TABLE trust_holding AS
        WITH trust_daily AS (
            SELECT
                date,
                market,
                symbol,
                MAX(name) AS name,
                SUM(COALESCE(trust_net, 0)) AS trust_net
            FROM institutional_investors
            GROUP BY date, market, symbol
        ),
        trust_cum AS (
            SELECT
                date,
                market,
                symbol,
                name,
                SUM(trust_net) OVER (
                    PARTITION BY market, symbol
                    ORDER BY date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS trust_held_shares
            FROM trust_daily
        )
        SELECT
            tc.date,
            tc.market,
            tc.symbol,
            COALESCE(fh.name, tc.name) AS name,
            fh.issued_shares,
            tc.trust_held_shares,
            CASE
                WHEN fh.issued_shares > 0 THEN ROUND((tc.trust_held_shares / fh.issued_shares * 100)::numeric, 4)
                ELSE NULL
            END AS trust_held_ratio,
            'calculated_trust_holding'::text AS pced_file,
            0::bigint AS pced_row,
            'x'::text AS pced_col
        FROM trust_cum tc
        LEFT JOIN foreign_holding fh
            ON tc.date = fh.date
           AND tc.market = fh.market
           AND tc.symbol = fh.symbol;
        """
    )

    with engine.begin() as conn:
        conn.execute(create_sql)
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_trust_holding_symbol_date ON trust_holding (symbol, date)"
            )
        )

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM trust_holding")).scalar()
        min_date, max_date = conn.execute(
            text("SELECT MIN(date), MAX(date) FROM trust_holding")
        ).fetchone()

    print(
        f"trust_holding rebuilt successfully: {total_rows} rows ({min_date} ~ {max_date})"
    )


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled trust_holding calculator error: {e}", e)


if __name__ == "__main__":
    main()
