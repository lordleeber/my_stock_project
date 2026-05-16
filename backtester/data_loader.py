from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from common.db import get_db_url


# 候選股 CSV 必須包含的欄位；缺少任一欄位會在載入時提前失敗，避免後續計算出現隱性錯誤
REQUIRED_CANDIDATE_COLUMNS = {"symbol", "predict_target_price", "close", "entry_date"}


def load_candidates(path: Path) -> pd.DataFrame:
    """載入候選股清單 CSV，做基本型別轉換與缺值過濾。

    回傳值保證：
      - symbol 為去空白的字串
      - entry_date 為 pd.Timestamp（已剔除無法解析的列）
      - predict_target_price / close 已轉為數值（允許 NaN）
    """
    if not path.exists():
        raise FileNotFoundError(f"candidates not found: {path}")

    df = pd.read_csv(path)
    # 提前驗證欄位完整性，缺欄位代表上游流程有問題
    missing = REQUIRED_CANDIDATE_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"candidates missing required columns: {sorted(missing)}")

    out = df.copy()
    out["symbol"] = out["symbol"].astype(str).str.strip()
    out["entry_date"] = pd.to_datetime(out["entry_date"], errors="coerce")
    out["predict_target_price"] = pd.to_numeric(
        out["predict_target_price"], errors="coerce"
    )
    out["close"] = pd.to_numeric(out["close"], errors="coerce")

    # 剔除 symbol 或 entry_date 無效的列，這些列無法參與回測
    out = out.dropna(subset=["symbol", "entry_date"])
    out = out[out["symbol"] != ""].copy()
    if out.empty:
        raise RuntimeError("candidates exists but has no usable symbol/entry_date rows")
    return out.reset_index(drop=True)


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


def estimate_quote_window(
    candidates: pd.DataFrame, max_hold_days: int
) -> tuple[str, str]:
    """依候選股的 entry_date 範圍估算需要撈取的行情時間窗口。

    結束日加上足夠的日曆天緩衝（至少 60 天，或持有天數 ×3），
    以確保最大持有期間（以交易日計）都落在撈取範圍內。
    """
    # 給足夠的日曆天緩衝，以涵蓋以交易日計算的最大持有天數。
    start = candidates["entry_date"].min().date()
    end = candidates["entry_date"].max().date() + timedelta(
        days=max(60, max_hold_days * 3)
    )
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


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
