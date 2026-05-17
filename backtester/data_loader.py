from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url


def normalize_quotes(df: pd.DataFrame) -> pd.DataFrame:
    """標準化行情 DataFrame：統一型別、剔除缺值、去除重複日期（保留最後一筆）。

    重複日期通常來自合併多個資料來源；keep='last' 保留最新寫入的版本。
    """
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    # 剔除 symbol 或 date 無效的列（資料庫寫入異常時可能發生）
    out = out.dropna(subset=["symbol", "date"]).copy()
    return (
        out.sort_values(["symbol", "date"])
        .drop_duplicates(subset=["symbol", "date"], keep="last")
        .reset_index(drop=True)
    )


def fetch_quotes_from_db(
    symbols: list[str], start_date: str, end_date: str
) -> pd.DataFrame:
    """從 daily_quotes 撈取指定股票在日期區間內的 OHLC 行情。

    使用 SQLAlchemy expanding bindparam 處理 IN 子句，避免 SQL injection 並支援大量股票代碼。
    回傳值已經過 normalize_quotes 處理（型別統一、去重）。
    """
    if not symbols:
        raise ValueError("symbols is empty")

    # expanding=True 讓 SQLAlchemy 把 list 展開為 (:symbols_0, :symbols_1, ...)
    stmt = text(
        """
        SELECT symbol, date, open, high, low, close
        FROM daily_quotes
        WHERE symbol IN :symbols
          AND date >= :start_date
          AND date <= :end_date
        """
    ).bindparams(bindparam("symbols", expanding=True))

    engine = create_engine(get_db_url())
    with engine.connect() as conn:
        out = pd.read_sql(
            stmt,
            conn,
            params={"symbols": symbols, "start_date": start_date, "end_date": end_date},
        )
    return normalize_quotes(out)
