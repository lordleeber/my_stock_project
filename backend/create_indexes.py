from sqlalchemy import create_engine, text
import os


def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def add_indexes():
    db_url = get_db_url()
    engine = create_engine(db_url)

    conn = engine.connect()
    try:
        print("Creating indexes...")
        # 建立複合索引以加速查詢
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_daily_quotes_date_symbol ON daily_quotes (date, symbol)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_daily_quotes_symbol_date ON daily_quotes (symbol, date)"
            )
        )

        # ML training data optimization indexes
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_technical_indicators_symbol_date ON technical_indicators (symbol, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_institutional_investors_symbol_date ON institutional_investors (symbol, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_foreign_holding_symbol_date ON foreign_holding (symbol, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_trust_holding_symbol_date ON trust_holding (symbol, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_dealer_holding_symbol_date ON dealer_holding (symbol, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_shareholding_concentration_symbol_date ON shareholding_concentration (symbol, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_short_interest_analysis_symbol_date ON short_interest_analysis (symbol, date)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_margin_pressure_analysis_symbol_date ON margin_pressure_analysis (symbol, date)"
            )
        )

        print("Indexes created successfully.")
    except Exception as e:
        print(f"Error creating indexes: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    add_indexes()
