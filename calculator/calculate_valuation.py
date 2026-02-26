import datetime
import os
import traceback
import sys
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# 加入 common 目錄到搜尋路徑
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.schemas import get_polars_schema, SCHEMA_COLS

ERROR_LOG = "/error_valuation_calculator.log"

def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def get_publish_date(q_str):
    """計算財報官方公佈截止日 (生效日)"""
    year = int(q_str[:4])
    q = q_str[5]
    if q == '1': return f"{year}-05-15"
    if q == '2': return f"{year}-08-14"
    if q == '3': return f"{year}-11-14"
    return f"{year+1}-03-31"

def get_next_quarter(q_str):
    year = int(q_str[:4])
    q = int(q_str[5])
    if q == 4: return f"{year+1}Q1"
    return f"{year}Q{q+1}"

def run():
    print("Starting Point-in-Time Valuation Calculator (Fixed Bias)...")
    engine = create_engine(get_db_url())

    # 1. 抓取所有歷史 EPS 數據
    df_eps = pd.read_sql("SELECT date, symbol, eps_q, nav_per_share FROM quarterly_reports ORDER BY symbol, date", engine)
    df_prices = pd.read_sql("SELECT date, symbol, close FROM daily_quotes ORDER BY symbol, date", engine)
    df_official_pe = pd.read_sql("SELECT date, symbol, pe_ratio as pe_official FROM pe_ratio", engine)
    df_preds = pd.read_sql("SELECT symbol, target_quarter, predict_eps FROM eps_predictions", engine)
    
    # 2. 計算全歷史的 TTM EPS 序列
    print("Pre-calculating all historical TTM sequences...")
    df_eps = df_eps.sort_values(['symbol', 'date'])
    df_eps['ttm_eps_official'] = df_eps.groupby('symbol')['eps_q'].transform(lambda x: x.rolling(window=4).sum())
    # Forward TTM 基礎 (前三季實質)
    df_eps['latest_3_sum'] = df_eps.groupby('symbol')['eps_q'].transform(lambda x: x.rolling(window=3).sum())
    
    # 設定財報生效日 (這是 Point-in-Time 的關鍵)
    df_eps['publish_date'] = pd.to_datetime(df_eps['date'].apply(get_publish_date))
    
    # 3. 處理預測值 (併入 TTM 序列)
    # 這裡我們做一個簡化：假設預測值在該季報生效日當天就產出了
    df_eps['next_q'] = df_eps['date'].apply(get_next_quarter)
    df_eps = df_eps.merge(df_preds, left_on=['symbol', 'next_q'], right_on=['symbol', 'target_quarter'], how='left')
    df_eps['ttm_eps_forward'] = df_eps['latest_3_sum'] + df_eps['predict_eps'].fillna(0)
    df_eps.loc[df_eps['predict_eps'].isna(), 'ttm_eps_forward'] = df_eps['ttm_eps_official']

    # 4. 執行 Point-in-Time 合併 (merge_asof)
    print("Executing Point-in-Time join (Daily Price <-> Latest Published Report)...")
    df_prices['date_ts'] = pd.to_datetime(df_prices['date'])
    df_eps = df_eps.sort_values('publish_date')
    
    # 對每一天，抓取當時「已公佈」的最新財報 TTM
    df_combined = pd.merge_asof(
        df_prices.sort_values('date_ts'),
        df_eps[['symbol', 'publish_date', 'ttm_eps_official', 'ttm_eps_forward', 'nav_per_share']].dropna(subset=['ttm_eps_official']),
        left_on='date_ts',
        right_on='publish_date',
        by='symbol',
        direction='backward'
    )

    # 5. 合併官方 PE 並計算指標
    print("Calculating PE, Target Prices and Upside...")
    df_combined = df_combined.merge(df_official_pe, on=['symbol', 'date'], how='left')
    
    # 排除無效數據
    df_combined = df_combined[(df_combined['ttm_eps_official'] > 0) & (df_combined['ttm_eps_forward'] > 0)]
    
    df_combined['pe_calculated'] = (df_combined['close'] / df_combined['ttm_eps_official']).round(2)
    df_combined['pe_forward'] = (df_combined['close'] / df_combined['ttm_eps_forward']).round(2)
    df_combined['predict_target_price'] = (df_combined['ttm_eps_forward'] * df_combined['pe_official']).round(2)
    df_combined['upside_pct'] = ((df_combined['predict_target_price'] / df_combined['close'] - 1) * 100).round(2)
    df_combined['roe_official'] = (df_combined['ttm_eps_official'] / df_combined['nav_per_share'] * 100).round(2)
    df_combined['roe_forward'] = (df_combined['ttm_eps_forward'] / df_combined['nav_per_share'] * 100).round(2)

    # 6. 計算歷史排名 (Percentile)
    # 這是真正的歷史位階：拿今天的 PE 去跟該股票「過去所有歷史 PE」比
    print("Ranking historical percentiles (Point-in-Time)...")
    # Full-history percentile rank within each symbol.
    df_combined['pe_percentile_official'] = (
        df_combined.groupby('symbol')['pe_calculated'].rank(pct=True).round(4) * 100
    )
    df_combined['pe_percentile_forward'] = (
        df_combined.groupby('symbol')['pe_forward'].rank(pct=True).round(4) * 100
    )
    df_final_grouped = df_combined

    # 7. 存入資料庫
    print(f"Writing {len(df_final_grouped)} rows to valuation_daily...")
    df_final_grouped['date'] = df_final_grouped['date_ts'].dt.strftime('%Y-%m-%d')
    
    final_cols = SCHEMA_COLS['valuation_daily']
    df_final_grouped['pced_file'] = 'calculated_pit'
    df_final_grouped['pced_row'] = 0
    df_final_grouped['pced_col'] = 'x'
    
    output_df = df_final_grouped[[c for c in final_cols if c in df_final_grouped.columns]]
    
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS valuation_daily"))
        conn.commit()
        
    output_df.to_sql("valuation_daily", engine, if_exists="replace", index=False, chunksize=5000)
    
    with engine.connect() as conn:
        conn.execute(text("CREATE INDEX idx_val_daily_symbol_date ON valuation_daily (symbol, date)"))
        conn.commit()

    print("Point-in-Time Valuation Calculator finished successfully.")

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        sys.exit(1)
