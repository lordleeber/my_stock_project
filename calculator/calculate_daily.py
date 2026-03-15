import datetime
import os
import traceback

import pandas as pd
from sqlalchemy import create_engine, text


ERROR_LOG = "/error_calculator.log"


def abort_with_error(message, exception=None):
    with open(ERROR_LOG, "w") as f:
        f.write("# Calculator 錯誤報告\n\n")
        f.write(
            f"執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        )
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


def get_engine():
    return create_engine(get_db_url())


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return pd.to_datetime(date_str)
    except Exception as e:
        raise ValueError(
            f"Invalid date format: {date_str}. Expected YYYYMMDD or YYYY-MM-DD."
        ) from e


def get_target_range_from_env(required=False):
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")

    if required and (not start_date_env or not end_date_env):
        raise ValueError("START_DATE and END_DATE are both required.")

    start_ts = _parse_date(start_date_env)
    end_ts = _parse_date(end_date_env) if end_date_env else None

    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise ValueError(
            f"START_DATE must be <= END_DATE (START_DATE={start_date_env}, END_DATE={end_date_env})"
        )

    return start_ts, end_ts


def calculate_net_streak(net_series):
    # Buy streak => positive days, sell streak => negative days, flat => 0.
    signs = net_series.fillna(0).apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    streak = pd.Series(0, index=net_series.index, dtype="int64")

    non_zero = signs != 0
    if non_zero.any():
        segment = (signs != signs.shift(1)).cumsum()
        run_len = signs.groupby(segment).cumcount() + 1
        streak.loc[non_zero] = (run_len * signs).loc[non_zero].astype("int64")

    return streak


def calculate_indicators(df_group):
    symbol = df_group.name
    df_group = df_group.sort_values("date").copy()
    close = df_group["close"]

    df_group["ma5"] = close.rolling(window=5).mean()
    df_group["ma10"] = close.rolling(window=10).mean()
    df_group["ma20"] = close.rolling(window=20).mean()
    df_group["ma60"] = close.rolling(window=60).mean()
    df_group["ma120"] = close.rolling(window=120).mean()
    df_group["ma240"] = close.rolling(window=240).mean()

    df_group["vma5"] = df_group["volume"].rolling(window=5).mean()
    df_group["vma10"] = df_group["volume"].rolling(window=10).mean()
    df_group["vma20"] = df_group["volume"].rolling(window=20).mean()
    df_group["vma60"] = df_group["volume"].rolling(window=60).mean()
    df_group["vma120"] = df_group["volume"].rolling(window=120).mean()
    df_group["vma240"] = df_group["volume"].rolling(window=240).mean()

    low_9 = df_group["low"].rolling(window=9).min()
    high_9 = df_group["high"].rolling(window=9).max()
    rsv = (close - low_9) / (high_9 - low_9) * 100
    rsv = rsv.fillna(50)
    df_group["k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    df_group["d"] = df_group["k"].ewm(alpha=1 / 3, adjust=False).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    def calculate_rsi(series_gain, series_loss, window):
        avg_gain = series_gain.ewm(com=window - 1, min_periods=window).mean()
        avg_loss = series_loss.ewm(com=window - 1, min_periods=window).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    df_group["rsi6"] = calculate_rsi(gain, loss, 6)
    df_group["rsi12"] = calculate_rsi(gain, loss, 12)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df_group["macd_dif"] = ema12 - ema26
    df_group["macd_dea"] = df_group["macd_dif"].ewm(span=9, adjust=False).mean()
    df_group["macd_hist"] = df_group["macd_dif"] - df_group["macd_dea"]

    std20 = close.rolling(window=20).std()
    df_group["bb_middle"] = df_group["ma20"]
    df_group["bb_upper"] = df_group["bb_middle"] + 2 * std20
    df_group["bb_lower"] = df_group["bb_middle"] - 2 * std20

    df_group["foreign_streak_days"] = calculate_net_streak(df_group["foreign_net"])
    df_group["trust_streak_days"] = calculate_net_streak(df_group["trust_net"])
    df_group["dealer_streak_days"] = calculate_net_streak(df_group["dealer_net"])

    df_group["symbol"] = symbol

    return df_group[
        [
            "date",
            "symbol",
            "ma5",
            "ma10",
            "ma20",
            "ma60",
            "ma120",
            "ma240",
            "vma5",
            "vma10",
            "vma20",
            "vma60",
            "vma120",
            "vma240",
            "k",
            "d",
            "rsi6",
            "rsi12",
            "macd_dif",
            "macd_dea",
            "macd_hist",
            "bb_upper",
            "bb_middle",
            "bb_lower",
            "foreign_streak_days",
            "trust_streak_days",
            "dealer_streak_days",
        ]
    ]


def ensure_streak_columns(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS foreign_streak_days bigint"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS trust_streak_days bigint"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS dealer_streak_days bigint"
            )
        )


def run():
    print("Starting Calculator (daily)...")
    engine = get_engine()

    start_ts, end_ts = get_target_range_from_env(required=False)

    if start_ts is not None:
        start_date = start_ts.date()
        end_date = end_ts.date() if end_ts is not None else None
        if end_date:
            print(f"Incremental Mode: {start_date} ~ {end_date}")
        else:
            print(f"Incremental Mode: >= {start_date}")

        buffer_date = (start_ts - pd.Timedelta(days=500)).strftime("%Y-%m-%d")
        query = text(
            "SELECT dq.date, dq.symbol, dq.high, dq.low, dq.close, dq.volume, "
            "       ii.foreign_net, ii.trust_net, ii.dealer_net "
            "FROM daily_quotes dq "
            "LEFT JOIN institutional_investors ii ON dq.date = ii.date AND dq.symbol = ii.symbol "
            "WHERE dq.date >= :buffer_date ORDER BY dq.symbol, dq.date"
        )
        df = pd.read_sql(query, engine, params={"buffer_date": buffer_date})
        if_exists_mode = "append"
        is_incremental = True
    else:
        print("Full Calculation Mode (ALL history)")
        query = text(
            "SELECT dq.date, dq.symbol, dq.high, dq.low, dq.close, dq.volume, "
            "       ii.foreign_net, ii.trust_net, ii.dealer_net "
            "FROM daily_quotes dq "
            "LEFT JOIN institutional_investors ii ON dq.date = ii.date AND dq.symbol = ii.symbol "
            "ORDER BY dq.symbol, dq.date"
        )
        df = pd.read_sql(query, engine)
        if_exists_mode = "replace"
        is_incremental = False
        start_date = None
        end_date = None

    if df.empty:
        print("No data found in daily_quotes.")
        return

    print(f"Data fetched: {len(df)} rows. Calculating indicators...")
    results = df.groupby("symbol", group_keys=False).apply(
        calculate_indicators, include_groups=False
    )

    if is_incremental:
        results["date"] = pd.to_datetime(results["date"]).dt.date
        mask = results["date"] >= start_date
        if end_date is not None:
            mask = mask & (results["date"] <= end_date)
        results = results[mask]

        print(f"Filtered result rows: {len(results)}")
        if not results.empty:
            start_str = start_date.strftime("%Y-%m-%d")
            with engine.connect() as conn:
                table_exists = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_name='technical_indicators')"
                    )
                ).scalar()
                if table_exists:
                    if end_date is not None:
                        end_str = end_date.strftime("%Y-%m-%d")
                        delete_query = text(
                            "DELETE FROM technical_indicators WHERE date::date >= :start_date AND date::date <= :end_date"
                        )
                        conn.execute(
                            delete_query, {"start_date": start_str, "end_date": end_str}
                        )
                    else:
                        delete_query = text(
                            "DELETE FROM technical_indicators WHERE date::date >= :start_date"
                        )
                        conn.execute(delete_query, {"start_date": start_str})
                    conn.commit()

    if not results.empty:
        if is_incremental:
            ensure_streak_columns(engine)
        print(f"Writing {len(results)} rows (mode={if_exists_mode})...")
        results.to_sql(
            "technical_indicators",
            engine,
            if_exists=if_exists_mode,
            index=False,
            chunksize=5000,
        )

    if not is_incremental:
        with engine.connect() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_tech_symbol_date ON technical_indicators (symbol, date)"
                )
            )
            conn.commit()

    print("Calculator (daily) finished successfully.")


def main():
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled daily calculator error: {e}", e)


if __name__ == "__main__":
    main()
