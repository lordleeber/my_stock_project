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
    print("Starting Short Interest Analysis Calculator...")
    engine = create_engine(get_db_url())

    create_sql = text(
        """
        DROP TABLE IF EXISTS short_interest_analysis;

        CREATE TABLE short_interest_analysis AS
        WITH base AS (
            SELECT
                date,
                market,
                symbol,
                MAX(name) AS name,
                SUM(COALESCE(sbl_balance, 0)) AS sbl_balance,
                SUM(COALESCE(sbl_prev_balance, 0)) AS sbl_prev_balance,
                SUM(COALESCE(sbl_sell, 0)) AS sbl_sell,
                SUM(COALESCE(sbl_repay, 0)) AS sbl_repay,
                SUM(COALESCE(margin_short_balance, 0)) AS margin_short_balance,
                SUM(COALESCE(margin_short_prev_balance, 0)) AS margin_short_prev_balance
            FROM margin_sbl
            GROUP BY date, market, symbol
        ),
        with_delta AS (
            SELECT
                date,
                market,
                symbol,
                name,
                sbl_balance,
                sbl_balance - sbl_prev_balance AS sbl_balance_wow,
                CASE
                    WHEN sbl_prev_balance > 0 THEN (sbl_balance - sbl_prev_balance) / sbl_prev_balance * 100
                    ELSE NULL
                END AS sbl_balance_wow_pct,
                sbl_sell,
                sbl_repay,
                CASE
                    WHEN sbl_repay > 0 THEN sbl_sell / sbl_repay
                    ELSE NULL
                END AS sbl_sell_repay_ratio,
                margin_short_balance,
                margin_short_balance - margin_short_prev_balance AS margin_short_balance_wow,
                CASE
                    WHEN margin_short_prev_balance > 0 THEN (margin_short_balance - margin_short_prev_balance) / margin_short_prev_balance * 100
                    ELSE NULL
                END AS margin_short_balance_wow_pct
            FROM base
        )
        SELECT
            date,
            market,
            symbol,
            name,
            sbl_balance,
            ROUND(sbl_balance_wow::numeric, 4) AS sbl_balance_wow,
            ROUND(sbl_balance_wow_pct::numeric, 4) AS sbl_balance_wow_pct,
            sbl_sell,
            sbl_repay,
            ROUND(sbl_sell_repay_ratio::numeric, 4) AS sbl_sell_repay_ratio,
            margin_short_balance,
            ROUND(margin_short_balance_wow::numeric, 4) AS margin_short_balance_wow,
            ROUND(margin_short_balance_wow_pct::numeric, 4) AS margin_short_balance_wow_pct,
            ROUND(
                (
                    COALESCE(sbl_balance_wow_pct, 0) * 0.4
                    + COALESCE(margin_short_balance_wow_pct, 0) * 0.4
                    + (COALESCE(sbl_sell_repay_ratio, 1) - 1) * 100 * 0.2
                )::numeric,
                4
            ) AS short_pressure_score,
            'calculated_short_interest_analysis'::text AS pced_file,
            0::bigint AS pced_row,
            'x'::text AS pced_col
        FROM with_delta;
        """
    )

    with engine.begin() as conn:
        conn.execute(create_sql)
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_short_interest_analysis_symbol_date "
                "ON short_interest_analysis (symbol, date)"
            )
        )

    with engine.connect() as conn:
        total_rows = conn.execute(
            text("SELECT COUNT(*) FROM short_interest_analysis")
        ).scalar()
        min_date, max_date = conn.execute(
            text("SELECT MIN(date), MAX(date) FROM short_interest_analysis")
        ).fetchone()

    print(
        "short_interest_analysis rebuilt successfully: "
        f"{total_rows} rows ({min_date} ~ {max_date})"
    )


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled short_interest_analysis calculator error: {e}", e)


if __name__ == "__main__":
    main()
