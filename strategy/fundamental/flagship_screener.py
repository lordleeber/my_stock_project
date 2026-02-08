import pandas as pd
import requests
import sys
import numpy as np
import os
import time
from datetime import datetime, timedelta

# ---------------------------------------------------------
# 基本面旗艦級選股系統 5.2 (完整歷史批次版)
# ---------------------------------------------------------

API_BASE = "http://100.103.191.79:8000"

def get_20th_business_day(year, month):
    count = 0
    curr = datetime(year, month, 1)
    while count < 20:
        if curr.weekday() < 5:
            count += 1
        if count < 20:
            curr += timedelta(days=1)
    return curr.strftime("%Y-%m-%d")

def score_linear(val, min_val, max_val):
    if pd.isna(val): return 0
    if val <= min_val: return 0
    if val >= max_val: return 100
    return (val - min_val) / (max_val - min_val) * 100

def is_regular_stock(symbol):
    s = str(symbol).strip()
    return s.isdigit() and len(s) == 4 and not s.startswith(('00', '02', '91', '01'))

def get_config_for_quarter(q_str):
    year = int(q_str[:4])
    q = q_str[4:]
    if q == "Q1":
        sim_date = get_20th_business_day(year, 6)
        rev_months = [f"{year}M03", f"{year}M04", f"{year}M05"]
    elif q == "Q2":
        sim_date = get_20th_business_day(year, 9)
        rev_months = [f"{year}M06", f"{year}M07", f"{year}M08"]
    elif q == "Q3":
        sim_date = get_20th_business_day(year, 12)
        rev_months = [f"{year}M09", f"{year}M10", f"{year}M11"]
    elif q == "Q4":
        sim_date = get_20th_business_day(year + 1, 4)
        rev_months = [f"{year+1}M01", f"{year+1}M02", f"{year+1}M03"]
    else: return None, None
    return sim_date, rev_months

def process_quarter(q_str):
    sim_date, rev_months = get_config_for_quarter(q_str)
    print(f">>> 正在處理 {q_str} (公告模擬日: {sim_date})...")
    
    try:
        df_q = pd.DataFrame(requests.get(f"{API_BASE}/raw/quarterly-reports?start_date={q_str}&end_date={q_str}&limit=3000").json())
        df_cf = pd.DataFrame(requests.get(f"{API_BASE}/raw/cash-flows?start_date={q_str}&end_date={q_str}&limit=3000").json())
        df_p = pd.DataFrame(requests.get(f"{API_BASE}/raw/daily-quotes?start_date={sim_date}&end_date={sim_date}&limit=5000").json())
        df_info = pd.DataFrame(requests.get(f"{API_BASE}/raw/stock-info?limit=5000").json())
        
        if df_p.empty:
            curr = datetime.strptime(sim_date, "%Y-%m-%d")
            for _ in range(5):
                curr += timedelta(days=1)
                d_str = curr.strftime("%Y-%m-%d")
                df_p = pd.DataFrame(requests.get(f"{API_BASE}/raw/daily-quotes?start_date={d_str}&end_date={d_str}&limit=5000").json())
                if not df_p.empty: 
                    sim_date = d_str
                    break

        all_rev = []
        for m in rev_months:
            r = requests.get(f"{API_BASE}/raw/monthly-revenue?start_date={m}&end_date={m}&limit=3000").json()
            if r: all_rev.extend(r)
        df_r = pd.DataFrame(all_rev)

        if df_q.empty or df_p.empty or df_r.empty:
            print(f"  [跳過] 資料不足 (Q:{len(df_q)} P:{len(df_p)} R:{len(df_r)})")
            return

        for d in [df_q, df_cf, df_p, df_r, df_info]: d['symbol'] = d['symbol'].astype(str)
        df_p = df_p[df_p['symbol'].apply(is_regular_stock)]
        df_r['yoy_pct'] = pd.to_numeric(df_r['yoy_pct'], errors='coerce')
        rev_trend = df_r.sort_values(['symbol', 'date']).groupby('symbol').agg({'yoy_pct': ['mean', 'last']}).reset_index()
        rev_trend.columns = ['symbol', 'rev_avg_3m', 'rev_latest_yoy']

        df = pd.merge(df_p[['symbol', 'name', 'close', 'pe_ratio']], df_q.drop(columns=['name', 'market'], errors='ignore'), on='symbol', how='left')
        df = pd.merge(df, df_cf[['symbol', 'cash_flow_operating']], on='symbol', how='left')
        df = pd.merge(df, rev_trend, on='symbol', how='left')
        df = pd.merge(df, df_info[['symbol', 'industry']], on='symbol', how='left')

        num_cols = ['revenue', 'op_income', 'net_income', 'eps_yoy', 'equity_to_assets_ratio', 'pe_ratio', 'rev_avg_3m', 'cash_flow_operating', 'close']
        for c in num_cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        df['op_margin'] = np.where(df['revenue'] > 0, (df['op_income'] / df['revenue']) * 100, 0)
        df['cash_quality'] = np.where(df['net_income'] > 0, df['cash_flow_operating'] / df['net_income'], 0)

        df_valid_pe = df[df['pe_ratio'] > 0].copy()
        ind_pe_map = df_valid_pe.groupby('industry')['pe_ratio'].median().to_dict()
        def calc_v(row):
            pe = row['pe_ratio']
            if pe <= 0: return 0
            base = ind_pe_map.get(row['industry'], 15)
            return score_linear(1.5 - (pe/base), 0, 1.0)

        df['value_score'] = df.apply(calc_v, axis=1)
        df['growth_score'] = df['eps_yoy'].apply(lambda x: score_linear(x, 0, 50))
        df['momentum_score'] = df['rev_avg_3m'].apply(lambda x: score_linear(x, 0, 20))
        df['quality_score'] = df['cash_quality'].apply(lambda x: score_linear(x, 0.5, 1.2))
        df['profit_score'] = df['op_margin'].apply(lambda x: score_linear(x, 5, 25))
        df['safety_score'] = df['equity_to_assets_ratio'].apply(lambda x: score_linear(x, 20, 60))

        df['total_score'] = (df['growth_score'] * 0.25) + (df['momentum_score'] * 0.20) + \
                            (df['quality_score'] * 0.20) + (df['profit_score'] * 0.15) + \
                            (df['safety_score'] * 0.10) + (df['value_score'] * 0.10)

        df = df.rename(columns={'close': 'market_price', 'rev_avg_3m': 'avg_revenue_yoy_3m'})
        df['price_date'] = sim_date
        df['report_quarter'] = q_str

        final_cols = [
            'symbol', 'name', 'industry', 'market_price', 'price_date', 'report_quarter',
            'pe_ratio', 'value_score', 'eps_yoy', 'growth_score',
            'avg_revenue_yoy_3m', 'momentum_score', 'op_margin', 'profit_score',
            'cash_quality', 'quality_score', 'equity_to_assets_ratio', 'safety_score',
            'total_score'
        ]
        
        final_df = df[final_cols].sort_values('total_score', ascending=False)
        output_path = os.path.join("strategy", "fundamental", f"fundamental_report_{q_str}.csv")
        final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"  [成功] 已產生報告，決策日：{sim_date}")

    except Exception as e:
        print(f"  [失敗] {q_str} 異常: {e}")

def main():
    quarters = []
    # 完整產生 2020Q1 到 2025Q3
    for y in range(2020, 2026):
        for q in ["Q1", "Q2", "Q3", "Q4"]:
            qs = f"{y}{q}"
            if y == 2025 and q == "Q4": break
            quarters.append(qs)
    
    print(f"啟動 2020-2025 完整批次報告產生器...")
    for q in quarters:
        process_quarter(q)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
