import pandas as pd
import requests
import numpy as np
import sys
import os

# ---------------------------------------------------------
# 基本面旗艦級估值系統 2.1 (欄位順序最終修正版)
# ---------------------------------------------------------

API_BASE = "http://100.103.191.79:8000"

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fetch_all_data():
    try:
        d_url = f"{API_BASE}/raw/daily-quotes?start_date=2025-01-01&end_date=2026-12-31&limit=1"
        latest_date = requests.get(d_url).json()[0]['date']
        is_stmt = pd.DataFrame(requests.get(f"{API_BASE}/raw/income-statements?start_date=2025Q3&end_date=2025Q3&limit=3000").json())
        bs_stmt = pd.DataFrame(requests.get(f"{API_BASE}/raw/balance-sheets?start_date=2025Q3&end_date=2025Q3&limit=3000").json())
        cf_stmt = pd.DataFrame(requests.get(f"{API_BASE}/raw/cash-flows?start_date=2025Q3&end_date=2025Q3&limit=3000").json())
        p_data = pd.DataFrame(requests.get(f"{API_BASE}/raw/daily-quotes?start_date={latest_date}&end_date={latest_date}&limit=5000").json())
        info = pd.DataFrame(requests.get(f"{API_BASE}/raw/stock-info?limit=5000").json())
        return is_stmt, bs_stmt, cf_stmt, p_data, info, latest_date
    except: return [pd.DataFrame()]*5 + [None]

def run_valuation():
    print("=== 基本面專家：旗艦級智能估值系統 2.1 ===")
    df_is, df_bs, df_cf, df_p, df_info, l_date = fetch_all_data()
    if df_p.empty: return

    for d in [df_is, df_bs, df_cf, df_p, df_info]:
        if not d.empty: d['symbol'] = d['symbol'].astype(str)

    df = pd.merge(df_p[['symbol', 'name', 'close', 'pe_ratio']], df_is[['symbol', 'eps', 'revenue', 'operating_income']], on='symbol', how='inner')
    df = pd.merge(df, df_bs[['symbol', 'nav_per_share', 'total_assets', 'total_equity']], on='symbol', how='inner')
    df = pd.merge(df, df_cf[['symbol', 'cash_flow_operating']], on='symbol', how='inner')
    df = pd.merge(df, df_info[['symbol', 'industry']], on='symbol', how='left')

    num_cols = ['close', 'pe_ratio', 'eps', 'nav_per_share', 'cash_flow_operating', 'total_assets', 'total_equity']
    for c in num_cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    industry_pe = df[df['pe_ratio'] > 0].groupby('industry')['pe_ratio'].median().to_dict()
    df['pb_ratio'] = df['close'] / df['nav_per_share']
    industry_pb = df[df['pb_ratio'] > 0].groupby('industry')['pb_ratio'].median().to_dict()

    df['fair_pe'] = df.apply(lambda r: r['eps'] * 4 * industry_pe.get(r['industry'], 15), axis=1)
    df['fair_pb'] = df.apply(lambda r: r['nav_per_share'] * industry_pb.get(r['industry'], 1.5), axis=1)
    df['price_graham'] = np.sqrt(np.maximum(0, 22.5 * (df['eps']*4) * df['nav_per_share']))
    df['fair_value'] = (df['fair_pe'] + df['fair_pb'] + df['price_graham']) / 3
    df['upside'] = (df['fair_value'] - df['close']) / df['close'] * 100
    df['roe_annual'] = (df['eps'] * 4 / df['nav_per_share']) * 100
    
    undervalued = df[(df['upside'] > 30) & (df['roe_annual'] > 10) & (df['eps'] > 0)].copy()
    undervalued = undervalued.sort_values('upside', ascending=False)
    undervalued['price_date'] = l_date
    undervalued = undervalued.rename(columns={'close': 'market_price'})

    # 欄位順序對調：price_date 在前, market_price 在後
    final_cols = [
        'symbol', 'name', 'industry', 'price_date', 'market_price', 
        'fair_value', 'upside', 'pe_ratio', 'eps', 'nav_per_share', 'roe_annual'
    ]
    
    output_path = os.path.join("strategy", "fundamental", "undervalued_picks.csv")
    undervalued[final_cols].to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"完成！已產生低估值報表，結果見 {output_path}")

if __name__ == "__main__":
    run_valuation()
