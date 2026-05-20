"""建立 / 補建主要熱表上的複合索引 (symbol, date)。

雖然原本是給 backend ML training data 端點用，但同樣的索引對 strategies / calculator
直連 DB 的 `WHERE symbol IN ... AND date <= ...` 模式同樣有效，因此搬到 tools/ 保留。

執行方式（host venv，預設打 localhost:5419，符合 common/db.py）：
    venv/bin/python3 tools/create_indexes.py
"""
from sqlalchemy import create_engine, text
import os


def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5419")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


INDEX_STMTS = [
    "CREATE INDEX IF NOT EXISTS idx_daily_quotes_date_symbol ON daily_quotes (date, symbol)",
    "CREATE INDEX IF NOT EXISTS idx_daily_quotes_symbol_date ON daily_quotes (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_technical_indicators_symbol_date ON technical_indicators (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_institutional_investors_symbol_date ON institutional_investors (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_foreign_holding_symbol_date ON foreign_holding (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_trust_holding_symbol_date ON trust_holding (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_dealer_holding_symbol_date ON dealer_holding (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_shareholding_concentration_symbol_date ON shareholding_concentration (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_short_interest_analysis_symbol_date ON short_interest_analysis (symbol, date)",
    "CREATE INDEX IF NOT EXISTS idx_margin_pressure_analysis_symbol_date ON margin_pressure_analysis (symbol, date)",
]


def add_indexes() -> None:
    engine = create_engine(get_db_url())
    with engine.begin() as conn:
        print("Creating indexes...")
        for stmt in INDEX_STMTS:
            conn.execute(text(stmt))
        print(f"Indexes created/verified: {len(INDEX_STMTS)} statements.")


if __name__ == "__main__":
    add_indexes()
