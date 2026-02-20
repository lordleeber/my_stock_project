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
    print("Starting Margin Pressure Analysis Calculator...")
    engine = create_engine(get_db_url())

    create_sql = text(
        """
        DROP TABLE IF EXISTS margin_pressure_analysis;

        CREATE TABLE margin_pressure_analysis AS
        WITH base AS (
            SELECT
                date,
                market,
                symbol,
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
            GROUP BY date, market, symbol
        )
        SELECT
            date,
            market,
            symbol,
            name,
            margin_long_balance,
            margin_long_limit,
            ROUND(
                CASE
                    WHEN margin_long_limit > 0 THEN margin_long_balance / margin_long_limit * 100
                    ELSE NULL
                END::numeric, 4
            ) AS margin_usage_ratio,
            ROUND((margin_long_balance - margin_long_prev_balance)::numeric, 4) AS margin_long_balance_wow,
            ROUND(
                CASE
                    WHEN margin_long_prev_balance > 0 THEN (margin_long_balance - margin_long_prev_balance) / margin_long_prev_balance * 100
                    ELSE NULL
                END::numeric, 4
            ) AS margin_long_balance_wow_pct,
            margin_short_balance,
            margin_short_limit,
            ROUND(
                CASE
                    WHEN margin_short_limit > 0 THEN margin_short_balance / margin_short_limit * 100
                    ELSE NULL
                END::numeric, 4
            ) AS short_usage_ratio,
            ROUND((margin_short_balance - margin_short_prev_balance)::numeric, 4) AS margin_short_balance_wow,
            ROUND(
                CASE
                    WHEN margin_short_prev_balance > 0 THEN (margin_short_balance - margin_short_prev_balance) / margin_short_prev_balance * 100
                    ELSE NULL
                END::numeric, 4
            ) AS margin_short_balance_wow_pct,
            ROUND(
                CASE
                    WHEN margin_short_prev_balance > 0 THEN (margin_short_buy + margin_short_cash_repay) / margin_short_prev_balance * 100
                    ELSE NULL
                END::numeric, 4
            ) AS short_cover_pressure,
            ROUND(
                (
                    COALESCE(
                        CASE
                            WHEN margin_long_limit > 0 THEN margin_long_balance / margin_long_limit * 100
                            ELSE NULL
                        END,
                        0
                    ) * 0.45
                    + COALESCE(
                        CASE
                            WHEN margin_short_limit > 0 THEN margin_short_balance / margin_short_limit * 100
                            ELSE NULL
                        END,
                        0
                    ) * 0.30
                    + COALESCE(
                        CASE
                            WHEN margin_short_prev_balance > 0 THEN (margin_short_buy + margin_short_cash_repay) / margin_short_prev_balance * 100
                            ELSE NULL
                        END,
                        0
                    ) * 0.25
                )::numeric,
                4
            ) AS margin_pressure_score,
            'calculated_margin_pressure_analysis'::text AS pced_file,
            0::bigint AS pced_row,
            'x'::text AS pced_col
        FROM base;
        """
    )

    with engine.begin() as conn:
        conn.execute(create_sql)
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_margin_pressure_analysis_symbol_date "
                "ON margin_pressure_analysis (symbol, date)"
            )
        )

    with engine.connect() as conn:
        total_rows = conn.execute(text("SELECT COUNT(*) FROM margin_pressure_analysis")).scalar()
        min_date, max_date = conn.execute(
            text("SELECT MIN(date), MAX(date) FROM margin_pressure_analysis")
        ).fetchone()

    print(
        "margin_pressure_analysis rebuilt successfully: "
        f"{total_rows} rows ({min_date} ~ {max_date})"
    )


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled margin_pressure_analysis calculator error: {e}", e)


if __name__ == "__main__":
    main()
