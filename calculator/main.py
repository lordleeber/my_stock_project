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
    
    return df_group[['date', 'symbol', 
                     'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma240',
                     'vma5', 'vma10', 'vma20', 'vma60', 'vma120', 'vma240']]

def main():
    print("Starting Calculator...")
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    print("Fetching data from DB...")
    # 這裡記得要包含 volume (前一次修復的點)
    query = "SELECT date, symbol, high, low, close, volume FROM daily_quotes ORDER BY symbol, date"
    df = pd.read_sql(query, engine)
    
    if df.empty:
        print("No data found in daily_quotes.")
        return

    print(f"Data fetched: {len(df)} rows. Calculating Indicators (MA, VMA)...")

    # 分組計算
    results = df.groupby('symbol', group_keys=False).apply(calculate_indicators)
    
    # 移除包含 NaN 的行 (指標初期)
    # 注意：MA240 需要 240 天資料，這會導致很多早期資料被 drop
    # 如果想保留短週期的值，可以不 dropna，或者針對特定列 dropna
    # 這裡為了簡單起見，我們先不 dropna，保留所有計算結果 (NaN 會存為 NULL)
    # results = results.dropna() 
    
    print(f"Calculation done. Writing {len(results)} rows to DB...")

    # 寫入 DB (這會自動更新 Schema，移除 k, d, rsi)
    results.to_sql('technical_indicators', engine, if_exists='replace', index=False, chunksize=5000)
    
    # 建立索引
    with engine.connect() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tech_symbol_date ON technical_indicators (symbol, date)"))
        # 移除舊的 k, rsi 索引，雖然 replace table 會自動 drop index，但為了保險可以不處理
        # 這裡只建立通用的查詢索引
        conn.commit()

    print("Calculator finished successfully.")

if __name__ == "__main__":
    main()
