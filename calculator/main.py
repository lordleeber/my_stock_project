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
    # 確保資料按日期排序
    df_group = df_group.sort_values('date')
    close = df_group['close']
    high = df_group['high']
    low = df_group['low']
    
    # --- 1. 計算 KD (9, 3, 3) ---
    low_min = low.rolling(window=9).min()
    high_max = high.rolling(window=9).max()
    rsv = 100 * (close - low_min) / (high_max - low_min)
    rsv = rsv.fillna(50)
    k = rsv.ewm(alpha=1/3, adjust=False).mean()
    d = k.ewm(alpha=1/3, adjust=False).mean()
    df_group['k'] = k
    df_group['d'] = d
    
    # --- 2. 計算 RSI (14) ---
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 使用 Wilder's Smoothing (alpha = 1/period)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    
    # 避免除以零
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    df_group['rsi'] = rsi

    # --- 3. 計算 MA (5, 10, 20, 60, 120, 240) ---
    df_group['ma5'] = close.rolling(window=5).mean()
    df_group['ma10'] = close.rolling(window=10).mean()
    df_group['ma20'] = close.rolling(window=20).mean()
    df_group['ma60'] = close.rolling(window=60).mean()
    df_group['ma120'] = close.rolling(window=120).mean()
    df_group['ma240'] = close.rolling(window=240).mean()
    
    return df_group[['date', 'symbol', 'k', 'd', 'rsi', 'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma240']]

def main():
    print("Starting Calculator...")
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    print("Fetching data from DB...")
    query = "SELECT date, symbol, high, low, close FROM daily_quotes ORDER BY symbol, date"
    df = pd.read_sql(query, engine)
    
    if df.empty:
        print("No data found in daily_quotes.")
        return

    print(f"Data fetched: {len(df)} rows. Calculating Indicators (KD, RSI)...")

    # 分組計算
    results = df.groupby('symbol', group_keys=False).apply(calculate_indicators)
    
    # 移除包含 NaN 的行 (指標初期)
    results = results.dropna()
    
    print(f"Calculation done. Writing {len(results)} rows to DB...")

    # 寫入 DB (這會自動增加 rsi 欄位)
    results.to_sql('technical_indicators', engine, if_exists='replace', index=False, chunksize=5000)
    
    # 建立索引
    with engine.connect() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tech_date_k ON technical_indicators (date, k)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tech_date_rsi ON technical_indicators (date, rsi)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tech_symbol_date ON technical_indicators (symbol, date)"))
        conn.commit()

    print("Calculator finished successfully.")

if __name__ == "__main__":
    main()