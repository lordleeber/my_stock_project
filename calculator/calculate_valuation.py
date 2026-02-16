import datetime
import os
import traceback
import sys
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

ERROR_LOG = "/error_valuation_calculator.log"

def abort_with_error(message, exception=None):
    with open(ERROR_LOG, "w") as f:
        f.write("# Valuation Calculator 錯誤報告\n\n")
        f.write(f"執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 錯誤訊息\n\n{message}\n\n")
        if exception is not None:
            f.write(f"## Traceback\n\n```\n{traceback.format_exc()}\n```\n")
    print(f"\n❌ {message}")
    sys.exit(1)

def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def run():
    print("Starting Valuation Calculator (Dual PE Mode)...")
    engine = create_engine(get_db_url())

    # 1. 抓取資料
    print("Fetching data from DB...")
    df_eps = pd.read_sql("SELECT date, symbol, eps_q FROM quarterly_reports", engine)
    df_prices = pd.read_sql("SELECT date, symbol, close FROM daily_quotes", engine)
    df_official_pe = pd.read_sql("SELECT date, symbol, pe_ratio as pe_ratio_from_pe_table FROM pe_ratio", engine)
    
    if df_eps.empty or df_prices.empty:
        print("Required data missing.")
        return

    # 2. 處理日期
    def q_to_date(q_str):
        y = int(q_str[:4])
        q = q_str[5]
        if q == '1': return f"{y}-03-31"
        if q == '2': return f"{y}-06-30"
        if q == '3': return f"{y}-09-30"
        return f"{y}-12-31"

    df_eps['date_ts'] = pd.to_datetime(df_eps['date'].apply(q_to_date))
    df_prices['date_ts'] = pd.to_datetime(df_prices['date'])
    df_official_pe['date_ts'] = pd.to_datetime(df_official_pe['date'])
    
    # 3. 計算 TTM EPS
    print("Calculating TTM EPS...")
    df_eps = df_eps.sort_values(['symbol', 'date_ts'])
    df_eps['ttm_eps'] = df_eps.groupby('symbol')['eps_q'].transform(lambda x: x.rolling(window=4).sum())
    
    # 4. 合併資料
    print("Merging data...")
    df_eps_clean = df_eps[['symbol', 'date_ts', 'ttm_eps']].dropna().sort_values('date_ts')
    
    # 使用 merge_asof 關聯股價與最新的 TTM EPS
    df_combined = pd.merge_asof(
        df_prices.sort_values('date_ts'),
        df_eps_clean,
        on='date_ts',
        by='symbol',
        direction='backward'
    )
    
    # 精確關聯官方 PE
    df_combined = df_combined.merge(
        df_official_pe[['symbol', 'date_ts', 'pe_ratio_from_pe_table']],
        on=['symbol', 'date_ts'],
        how='left'
    )
    
    # 5. 計算指標
    print("Calculating PE ratios...")
    df_combined = df_combined.dropna(subset=['ttm_eps', 'close'])
    df_combined = df_combined[df_combined['ttm_eps'] > 0]
    df_combined['pe_ratio_calculated'] = (df_combined['close'] / df_combined['ttm_eps']).round(2)
    
    # 6. 計算百分位排名
    print("Ranking percentiles...")
    # 使用 transform 避免索引遺失
    df_combined['pe_percentile'] = df_combined.groupby('symbol')['pe_ratio_calculated'].transform(
        lambda x: x.rank(pct=True).round(4) * 100
    )
    
    # 7. 準備存入資料庫
    print(f"Writing {len(df_combined)} rows to valuation_analysis...")
    df_combined['date'] = df_combined['date_ts'].dt.strftime('%Y-%m-%d')
    df_final = df_combined[['date', 'symbol', 'close', 'ttm_eps', 'pe_ratio_calculated', 'pe_ratio_from_pe_table', 'pe_percentile']].copy()
    
    df_final['pced_file'] = 'calculated'
    df_final['pced_row'] = 0
    df_final['pced_col'] = 'x'
    
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS valuation_analysis"))
        conn.commit()
        
    df_final.to_sql("valuation_analysis", engine, if_exists="replace", index=False, chunksize=5000)
    
    with engine.connect() as conn:
        conn.execute(text("CREATE INDEX idx_val_symbol_date ON valuation_analysis (symbol, date)"))
        conn.execute(text("CREATE INDEX idx_val_pe_pct ON valuation_analysis (pe_percentile)"))
        conn.commit()

    print("Valuation Calculator (Dual PE) finished successfully.")

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        abort_with_error(f"Unhandled valuation calculator error: {e}", e)
