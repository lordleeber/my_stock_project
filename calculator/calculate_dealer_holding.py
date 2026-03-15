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
    print("Starting Dealer Holding Calculator...")
    engine = create_engine(get_db_url())

    create_sql = text(
        """
        DROP TABLE IF EXISTS dealer_holding;

        CREATE TABLE dealer_holding AS
        WITH dealer_daily AS (
            SELECT
                date,
                market,
                symbol,
                MAX(name) AS name,
                SUM(COALESCE(dealer_net, 0)) AS dealer_net
            FROM institutional_investors
            GROUP BY date, market, symbol
        ),
        dealer_cum AS (
            SELECT
                date,
                market,
                symbol,
                name,
                SUM(dealer_net) OVER (
                    PARTITION BY market, symbol
                    ORDER BY date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS dealer_held_shares
            FROM dealer_daily
        )
        SELECT
            dc.date,
            dc.market,
            dc.symbol,
            COALESCE(fh.name, dc.name) AS name,
            fh.issued_shares,
            dc.dealer_held_shares,
            CASE
                WHEN fh.issued_shares > 0 THEN ROUND((dc.dealer_held_shares / fh.issued_shares * 100)::numeric, 4)
                ELSE NULL
            END AS dealer_held_ratio,
            'calculated_dealer_holding'::text AS pced_file,
            0::bigint AS pced_row,
            'x'::text AS pced_col
        FROM dealer_cum dc
        LEFT JOIN foreign_holding fh
            ON dc.date = fh.date
           AND dc.market = fh.market
           AND dc.symbol = fh.symbol;
        """
    )

    with engine.begin() as conn:
        conn.execute(create_sql)
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_dealer_holding_symbol_date ON dealer_holding (symbol, date)"
            )
        )

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM dealer_holding")).scalar()
        min_date, max_date = conn.execute(
            text("SELECT MIN(date), MAX(date) FROM dealer_holding")
        ).fetchone()

    print(
        f"dealer_holding rebuilt successfully: {total_rows} rows ({min_date} ~ {max_date})"
    )


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled dealer_holding calculator error: {e}", e)


if __name__ == "__main__":
    main()
