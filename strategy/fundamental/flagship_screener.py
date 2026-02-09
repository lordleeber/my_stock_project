import pandas as pd
import sys
import numpy as np
import os
from datetime import datetime, timedelta

# 加入專案根目錄到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.http_client import fetch_dataframe, fetch_json
from common.constants import API_BASE

# ---------------------------------------------------------
# 基本面旗艦級選股系統 5.7 (共用模組 + 重試機制)
# ---------------------------------------------------------

def get_20th_business_day(year, month):
    count = 0; curr = datetime(year, month, 1)
    while count < 20:
        if curr.weekday() < 5: count += 1
        if count < 20: curr += timedelta(days=1)
    return curr.strftime("%Y-%m-%d")

def score_linear(val, min_val, max_val):
    if pd.isna(val): return 0
    if val <= min_val: return 0
    if val >= max_val: return 100
    res = (val - min_val) / (max_val - min_val) * 100
    return round(float(res), 2)

def is_regular_stock(symbol):
    s = str(symbol).strip()
    return s.isdigit() and len(s) == 4 and not s.startswith(('00', '02', '91', '01'))

def get_config_for_quarter(q_str):
    year = int(q_str[:4]); q = q_str[4:]
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
    print(f">>> 正在處理 {q_str} (共用模組 + 重試機制)...")
    try:
        df_q = fetch_dataframe("/raw/quarterly-reports", {"start_date": q_str, "end_date": q_str, "limit": 3000})
        df_cf = fetch_dataframe("/raw/cash-flows", {"start_date": q_str, "end_date": q_str, "limit": 3000})
        df_p = fetch_dataframe("/raw/daily-quotes", {"start_date": sim_date, "end_date": sim_date, "limit": 5000})
        df_info = fetch_dataframe("/raw/stock-info", {"limit": 5000})

        actual_date = sim_date
        if df_p.empty:
            curr = datetime.strptime(sim_date, "%Y-%m-%d")
            for _ in range(10):
                curr += timedelta(days=1); d_str = curr.strftime("%Y-%m-%d")
                df_p = fetch_dataframe("/raw/daily-quotes", {"start_date": d_str, "end_date": d_str, "limit": 5000})
                if not df_p.empty: actual_date = d_str; break

        all_rev = []
        for m in rev_months:
            r = fetch_json("/raw/monthly-revenue", {"start_date": m, "end_date": m, "limit": 3000})
            if r: all_rev.extend(r)
        df_r = pd.DataFrame(all_rev)

        if df_q.empty or df_p.empty or df_r.empty: return

        for d in [df_q, df_cf, df_p, df_r, df_info]: d['symbol'] = d['symbol'].astype(str)
        df_p = df_p[df_p['symbol'].apply(is_regular_stock)]
        df_r['yoy_pct'] = pd.to_numeric(df_r['yoy_pct'], errors='coerce')
        rev_trend = df_r.sort_values(['symbol', 'date']).groupby('symbol').agg({'yoy_pct': ['mean', 'last']}).reset_index()
        rev_trend.columns = ['symbol', 'rev_avg_3m', 'rev_latest_yoy']

        df = pd.merge(df_p[['symbol', 'name', 'close', 'pe_ratio']], df_q.drop(columns=['name', 'market'], errors='ignore'), on='symbol', how='left')
        df = pd.merge(df, df_cf[['symbol', 'cash_flow_operating']], on='symbol', how='left')
        df = pd.merge(df, rev_trend, on='symbol', how='left')
        df = pd.merge(df, df_info[['symbol', 'industry']], on='symbol', how='left')

        num_cols = ['revenue', 'op_income', 'net_income', 'eps', 'eps_yoy', 'equity_to_assets_ratio', 'pe_ratio', 'rev_avg_3m', 'cash_flow_operating', 'close']
        for c in num_cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        df['op_margin'] = np.where(df['revenue'] > 0, (df['op_income'] / df['revenue']) * 100, 0)
        df['cash_quality'] = np.where(df['net_income'] > 0, df['cash_flow_operating'] / df['net_income'], 0)

        df_valid_pe = df[df['pe_ratio'] > 0].copy()
        ind_pe_map = df_valid_pe.groupby('industry')['pe_ratio'].median().to_dict()
        
        def calc_v_and_p(row):
            pe = row['pe_ratio']; ind = str(row['industry'])
            base_pe = ind_pe_map.get(ind, 12)
            v_score = score_linear(1.5 - (pe/base_pe), 0, 1.0) if pe > 0 else 0
            factor = 2 if ('建' in ind or '營造' in ind) else 4
            p_price = (row['eps'] * factor) * base_pe * 0.8
            return v_score, round(p_price, 2)

        df[['value_score', 'predict_price']] = df.apply(lambda r: pd.Series(calc_v_and_p(r)), axis=1)
        df['growth_score'] = df['eps_yoy'].apply(lambda x: score_linear(x, 0, 50))
        df['momentum_score'] = df['rev_avg_3m'].apply(lambda x: score_linear(x, 0, 20))
        df['quality_score'] = df['cash_quality'].apply(lambda x: score_linear(x, 0.5, 1.2))
        df['profit_score'] = df['op_margin'].apply(lambda x: score_linear(x, 5, 25))
        df['safety_score'] = df['equity_to_assets_ratio'].apply(lambda x: score_linear(x, 20, 60))

        df['total_score'] = (df['growth_score'] * 0.25) + (df['momentum_score'] * 0.20) + \
                            (df['quality_score'] * 0.20) + (df['profit_score'] * 0.15) + \
                            (df['safety_score'] * 0.10) + (df['value_score'] * 0.10)

        # 全域格式化至小數二位
        float_cols = df.select_dtypes(include=[np.float64, np.float32]).columns
        df[float_cols] = df[float_cols].round(2)

        df = df.rename(columns={'close': 'market_price', 'rev_avg_3m': 'avg_revenue_yoy_3m'})
        df['price_date'] = actual_date; df['report_quarter'] = q_str

        final_cols = [
            'symbol', 'name', 'industry', 'price_date', 'market_price', 'predict_price', 'report_quarter',
            'pe_ratio', 'value_score', 'eps_yoy', 'growth_score',
            'avg_revenue_yoy_3m', 'momentum_score', 'op_margin', 'profit_score',
            'cash_quality', 'quality_score', 'equity_to_assets_ratio', 'safety_score',
            'total_score'
        ]
        
        final_df = df[final_cols].sort_values('total_score', ascending=False)
        output_path = os.path.join("strategy", "fundamental", f"fundamental_report_{q_str}.csv")
        final_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"  [完成] {output_path}")

    except Exception as e:
        print(f"  [失敗] {q_str} 異常: {e}")

if __name__ == "__main__":
    for q in ["2024Q4", "2025Q1", "2025Q2", "2025Q3"]: process_quarter(q)
