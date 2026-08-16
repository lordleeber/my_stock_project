"""補建後來才加進 common/schemas.py 的欄位（idempotent）。

專案沒有 migration framework：新表由 importer 的 `to_sql(if_exists="append")` 依
DataFrame 自動建出來，所以**全新的 DB 不需要這支**。會用到它的只有一種情況 ——
既有的 DB（或從加欄之前的備份還原回來的 DB）少了某個欄位，而 processed CSV 已經
帶著它，`to_sql` append 進去就會炸。

沿用 tools/create_indexes.py 的作法：把 DDL 集中在一份可重跑的清單裡，而不是散在
各 importer 裡（importer 目前一行 DDL 都沒有，它的職責是把 CSV 灌進 DB）。
加了新欄位就往 COLUMN_STMTS append 一行。

執行方式（host venv，預設打 localhost:5419，符合 common/db.py）：
    venv/bin/python3 tools/sync_db_columns.py
"""

import os

from sqlalchemy import create_engine, text


def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5419")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


COLUMN_STMTS = [
    # 2026-08-16 個體財報：合併取 8610、個體取 8200，報表別一併入庫，
    # 下游才分得出哪一列是哪種基礎。見 processor/CLAUDE.md。
    "ALTER TABLE quarterly_reports_xbrl ADD COLUMN IF NOT EXISTS report_category TEXT",
]


def sync_columns() -> None:
    engine = create_engine(get_db_url())
    with engine.begin() as conn:
        print("Syncing columns...")
        for stmt in COLUMN_STMTS:
            conn.execute(text(stmt))
        print(f"Columns created/verified: {len(COLUMN_STMTS)} statements.")


if __name__ == "__main__":
    sync_columns()
