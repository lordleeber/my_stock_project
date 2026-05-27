import argparse
import datetime
import os
import sys
import traceback

import pandas as pd
from sqlalchemy import text

sys.path.append(os.path.dirname(__file__))
from _incremental import get_engine, get_last_processed_date


ERROR_LOG = "/error_calculator.log"
TABLE = "technical_indicators"
# MA240 needs ~480 trading days of history. 500 calendar days covers it.
BUFFER_DAYS = 500


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


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return pd.to_datetime(date_str)
    except Exception as e:
        raise ValueError(
            f"Invalid date format: {date_str}. Expected YYYYMMDD or YYYY-MM-DD."
        ) from e


def get_target_range_from_env():
    """START_DATE/END_DATE env vars override auto-detect. Returns (start_ts, end_ts)."""
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")

    start_ts = _parse_date(start_date_env)
    end_ts = _parse_date(end_date_env) if end_date_env else None

    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise ValueError(
            f"START_DATE must be <= END_DATE (START_DATE={start_date_env}, END_DATE={end_date_env})"
        )

    return start_ts, end_ts


def calculate_net_streak(net_series):
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
            "date", "symbol",
            "ma5", "ma10", "ma20", "ma60", "ma120", "ma240",
            "vma5", "vma10", "vma20", "vma60", "vma120", "vma240",
            "k", "d", "rsi6", "rsi12",
            "macd_dif", "macd_dea", "macd_hist",
            "bb_upper", "bb_middle", "bb_lower",
            "foreign_streak_days", "trust_streak_days", "dealer_streak_days",
        ]
    ]


def _create_table_if_missing(engine):
    with engine.begin() as conn:
        conn.execute(text(
            f"""
            CREATE TABLE IF NOT EXISTS {TABLE} (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                ma5 DOUBLE PRECISION, ma10 DOUBLE PRECISION, ma20 DOUBLE PRECISION,
                ma60 DOUBLE PRECISION, ma120 DOUBLE PRECISION, ma240 DOUBLE PRECISION,
                vma5 DOUBLE PRECISION, vma10 DOUBLE PRECISION, vma20 DOUBLE PRECISION,
                vma60 DOUBLE PRECISION, vma120 DOUBLE PRECISION, vma240 DOUBLE PRECISION,
                k DOUBLE PRECISION, d DOUBLE PRECISION,
                rsi6 DOUBLE PRECISION, rsi12 DOUBLE PRECISION,
                macd_dif DOUBLE PRECISION, macd_dea DOUBLE PRECISION, macd_hist DOUBLE PRECISION,
                bb_upper DOUBLE PRECISION, bb_middle DOUBLE PRECISION, bb_lower DOUBLE PRECISION,
                foreign_streak_days BIGINT, trust_streak_days BIGINT, dealer_streak_days BIGINT,
                PRIMARY KEY (date, symbol)
            )
            """
        ))
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS idx_tech_symbol_date ON {TABLE} (symbol, date)"
        ))


def run(force_full=False):
    print("Starting Calculator (daily)...")
    engine = get_engine()

    env_start_ts, env_end_ts = get_target_range_from_env()

    if force_full:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        print("Force-full mode: dropped existing table, recomputing all history.")
        start_ts = None
        end_ts = None
    elif env_start_ts is not None:
        # Explicit override (e.g. retry flow): use the env-supplied window
        start_ts = env_start_ts
        end_ts = env_end_ts
        print(
            f"Env override mode: {start_ts.date()} ~ "
            f"{end_ts.date() if end_ts is not None else 'latest'}"
        )
    else:
        # Auto-detect: pick up where we left off
        last_processed = get_last_processed_date(engine, TABLE)
        if last_processed is None:
            start_ts = None
            end_ts = None
            print("First run: computing full history.")
        else:
            start_ts = pd.to_datetime(last_processed) + pd.Timedelta(days=1)
            end_ts = None
            print(f"Incremental: appending rows from {start_ts.date()}")

    _create_table_if_missing(engine)

    if start_ts is None:
        query = text(
            "SELECT dq.date, dq.symbol, dq.high, dq.low, dq.close, dq.volume, "
            "       ii.foreign_net, ii.trust_net, ii.dealer_net "
            "FROM daily_quotes dq "
            "LEFT JOIN institutional_investors ii ON dq.date = ii.date AND dq.symbol = ii.symbol "
            "ORDER BY dq.symbol, dq.date"
        )
        df = pd.read_sql(query, engine)
        start_date = None
        end_date = None
    else:
        start_date = start_ts.date()
        end_date = end_ts.date() if end_ts is not None else None
        buffer_date = (start_ts - pd.Timedelta(days=BUFFER_DAYS)).strftime("%Y-%m-%d")
        query = text(
            "SELECT dq.date, dq.symbol, dq.high, dq.low, dq.close, dq.volume, "
            "       ii.foreign_net, ii.trust_net, ii.dealer_net "
            "FROM daily_quotes dq "
            "LEFT JOIN institutional_investors ii ON dq.date = ii.date AND dq.symbol = ii.symbol "
            "WHERE dq.date >= :buffer_date ORDER BY dq.symbol, dq.date"
        )
        df = pd.read_sql(query, engine, params={"buffer_date": buffer_date})

    if df.empty:
        print("No data found in daily_quotes.")
        return

    print(f"Data fetched: {len(df)} rows. Calculating indicators...")
    results = df.groupby("symbol", group_keys=False).apply(
        calculate_indicators, include_groups=False
    )

    if start_date is not None:
        results["date"] = pd.to_datetime(results["date"]).dt.date
        mask = results["date"] >= start_date
        if end_date is not None:
            mask = mask & (results["date"] <= end_date)
        results = results[mask]
        results["date"] = results["date"].astype(str)

        print(f"Filtered result rows: {len(results)}")
        if results.empty:
            print("Nothing to write.")
            return

        start_str = start_date.strftime("%Y-%m-%d")
        with engine.begin() as conn:
            if end_date is not None:
                end_str = end_date.strftime("%Y-%m-%d")
                conn.execute(
                    text(
                        f"DELETE FROM {TABLE} WHERE date >= :s AND date <= :e"
                    ),
                    {"s": start_str, "e": end_str},
                )
            else:
                conn.execute(
                    text(f"DELETE FROM {TABLE} WHERE date >= :s"),
                    {"s": start_str},
                )

    print(f"Writing {len(results)} rows...")
    results.to_sql(
        TABLE,
        engine,
        if_exists="append",
        index=False,
        chunksize=5000,
    )

    print("Calculator (daily) finished successfully.")


def main():
    parser = argparse.ArgumentParser(description="Compute technical_indicators incrementally.")
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Drop output table and recompute full history.",
    )
    args = parser.parse_args()
    try:
        run(force_full=args.force_full)
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Unhandled daily calculator error: {e}", e)


if __name__ == "__main__":
    main()
