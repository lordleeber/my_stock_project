import os
import pandas as pd
from sqlalchemy import create_engine, text

def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def calculate_indicators(df_group):
    """
    計算技術指標。
    注意：使用 include_groups=False 時，grouping column (symbol) 不會傳入，
    需要從 df_group.name 取得。
    """
    # 取得 symbol (groupby key)
    symbol = df_group.name

    # 確保資料按日期排序
    df_group = df_group.sort_values('date').copy()
    close = df_group['close']

    # --- 1. 計算 MA (5, 10, 20, 60, 120, 240) ---
    df_group['ma5'] = close.rolling(window=5).mean()
    df_group['ma10'] = close.rolling(window=10).mean()
    df_group['ma20'] = close.rolling(window=20).mean()
    df_group['ma60'] = close.rolling(window=60).mean()
    df_group['ma120'] = close.rolling(window=120).mean()
    df_group['ma240'] = close.rolling(window=240).mean()

    # --- 2. 計算 VMA (5, 10, 20, 60, 120, 240) ---
    df_group['vma5'] = df_group['volume'].rolling(window=5).mean()
    df_group['vma10'] = df_group['volume'].rolling(window=10).mean()
    df_group['vma20'] = df_group['volume'].rolling(window=20).mean()
    df_group['vma60'] = df_group['volume'].rolling(window=60).mean()
    df_group['vma120'] = df_group['volume'].rolling(window=120).mean()
    df_group['vma240'] = df_group['volume'].rolling(window=240).mean()

    # --- 3. 計算 KD (9, 3, 3) ---
    # RSV = (Close - Lowest_Low_9) / (Highest_High_9 - Lowest_Low_9) * 100
    low_9 = df_group['low'].rolling(window=9).min()
    high_9 = df_group['high'].rolling(window=9).max()
    rsv = (close - low_9) / (high_9 - low_9) * 100
    rsv = rsv.fillna(50)  # Fill NaN with 50 to avoid calculation errors at start

    # K = 2/3 * K_prev + 1/3 * RSV
    df_group['k'] = rsv.ewm(alpha=1/3, adjust=False).mean()

    # D = 2/3 * D_prev + 1/3 * K
    df_group['d'] = df_group['k'].ewm(alpha=1/3, adjust=False).mean()

    # --- 4. 計算 RSI (6, 12) ---
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    def calculate_rsi(series_gain, series_loss, window):
        avg_gain = series_gain.ewm(com=window-1, min_periods=window).mean()
        avg_loss = series_loss.ewm(com=window-1, min_periods=window).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    df_group['rsi6'] = calculate_rsi(gain, loss, 6)
    df_group['rsi12'] = calculate_rsi(gain, loss, 12)

    # --- 5. 計算 MACD (12, 26, 9) ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df_group['macd_dif'] = ema12 - ema26
    df_group['macd_dea'] = df_group['macd_dif'].ewm(span=9, adjust=False).mean()
    df_group['macd_hist'] = df_group['macd_dif'] - df_group['macd_dea']

    # --- 6. 計算 Bollinger Bands (20, 2) ---
    std20 = close.rolling(window=20).std()
    df_group['bb_middle'] = df_group['ma20']
    df_group['bb_upper'] = df_group['bb_middle'] + 2 * std20
    df_group['bb_lower'] = df_group['bb_middle'] - 2 * std20

    # 加入 symbol 欄位
    df_group['symbol'] = symbol

    return df_group[['date', 'symbol',
                     'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma240',
                     'vma5', 'vma10', 'vma20', 'vma60', 'vma120', 'vma240',
                     'k', 'd', 'rsi6', 'rsi12',
                     'macd_dif', 'macd_dea', 'macd_hist',
                     'bb_upper', 'bb_middle', 'bb_lower']]

def main():
    print("Starting Calculator...")
    db_url = get_db_url()
    engine = create_engine(db_url)

    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")

    # 模式判斷
    if start_date_env:
        # 解析日期 (保持為 pd.Timestamp 以便運算)
        target_start_ts = pd.to_datetime(start_date_env)
        target_end_ts = pd.to_datetime(end_date_env) if end_date_env else None

        # 轉換為 date 供後續比較
        target_start = target_start_ts.date()
        target_end = target_end_ts.date() if target_end_ts else None

        if target_end:
            print(f"Incremental Update Mode: Target Date {target_start} ~ {target_end}")
        else:
            print(f"Incremental Update Mode: Target Date >= {target_start}")

        # 1. 計算緩衝區起始日 (Buffer Date)
        # 我們需要足夠的歷史資料來計算 MA240 與 EMA 指標
        # 簡單起見，往回推 500 天 (約覆蓋 1.5 年以上的交易日)
        buffer_date = (target_start_ts - pd.Timedelta(days=500)).strftime('%Y-%m-%d')

        print(f"Fetching data with buffer from {buffer_date}...")

        # 使用參數化查詢避免 SQL Injection
        query = text("SELECT date, symbol, high, low, close, volume FROM daily_quotes WHERE date >= :buffer_date ORDER BY symbol, date")
        df = pd.read_sql(query, engine, params={"buffer_date": buffer_date})

        if_exists_mode = 'append'
        is_incremental = True

    else:
        print("Full Calculation Mode (Re-calculating ALL history)")
        print("Fetching data from DB...")
        target_start = None
        target_end = None
        query = text("SELECT date, symbol, high, low, close, volume FROM daily_quotes ORDER BY symbol, date")
        df = pd.read_sql(query, engine)

        if_exists_mode = 'replace'
        is_incremental = False

    if df.empty:
        print("No data found in daily_quotes.")
        return

    print(f"Data fetched: {len(df)} rows. Calculating Indicators...")

    # 分組計算 (加入 include_groups=False 避免 DeprecationWarning)
    results = df.groupby('symbol', group_keys=False).apply(calculate_indicators, include_groups=False)

    # 如果是增量更新，過濾掉 Buffer 期間的計算結果，只保留目標日期範圍內的資料
    if is_incremental:
        # 轉換為 date 型別（不含時間），確保與 DB 格式一致
        results['date'] = pd.to_datetime(results['date']).dt.date

        # 過濾：>= target_start
        mask = results['date'] >= target_start

        # 如果有 END_DATE，額外過濾 <= target_end
        if target_end:
            mask = mask & (results['date'] <= target_end)

        results = results[mask]

        print(f"Filtered results for Incremental Update: {len(results)} rows")

        if not results.empty:
            # Delete existing records for the target range to avoid duplicates
            # 使用參數化查詢，日期轉為字串格式
            start_date_str = target_start.strftime('%Y-%m-%d')
            with engine.connect() as conn:
                if target_end:
                    end_date_str = target_end.strftime('%Y-%m-%d')
                    print(f"Deleting existing records in technical_indicators {start_date_str} ~ {end_date_str}...")
                    delete_query = text("DELETE FROM technical_indicators WHERE date::date >= :start_date AND date::date <= :end_date")
                    conn.execute(delete_query, {"start_date": start_date_str, "end_date": end_date_str})
                else:
                    print(f"Deleting existing records in technical_indicators >= {start_date_str}...")
                    delete_query = text("DELETE FROM technical_indicators WHERE date::date >= :start_date")
                    conn.execute(delete_query, {"start_date": start_date_str})
                conn.commit()
    
    print(f"Writing {len(results)} rows to DB (Mode: {if_exists_mode})...")

    if not results.empty:
        results.to_sql('technical_indicators', engine, if_exists=if_exists_mode, index=False, chunksize=5000)
    
    # 建立索引 (僅在 Full Mode 或第一次建立時重要，但執行也不會報錯)
    if not is_incremental:
        with engine.connect() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tech_symbol_date ON technical_indicators (symbol, date)"))
            conn.commit()

    print("Calculator finished successfully.")

if __name__ == "__main__":
    main()
