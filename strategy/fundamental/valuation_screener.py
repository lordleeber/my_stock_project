import pandas as pd
import requests
import numpy as np
import sys

# ---------------------------------------------------------
# 基本面估值系統 (Valuation System) - 修正版
# ---------------------------------------------------------

API_BASE = "http://100.103.191.79:8000"

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fetch_data():
    try:
        d_url = f"{API_BASE}/raw/daily-quotes?start_date=2025-01-01&end_date=2026-12-31&limit=1"
        latest_date = requests.get(d_url).json()[0]['date']
        q_url = f"{API_BASE}/raw/daily-quotes?start_date={latest_date}&end_date={latest_date}&limit=5000"
        r_url = f"{API_BASE}/raw/quarterly-reports?start_date=2024-01-01&end_date=2026-12-31&limit=5000"
        rev_url = f"{API_BASE}/raw/monthly-revenue?start_date=2025-10-01&end_date=2026-12-31&limit=5000"

        print("正在獲取資料...")
        quotes = pd.DataFrame(requests.get(q_url, timeout=40).json())
        reports = pd.DataFrame(requests.get(r_url, timeout=40).json())
        revenue = pd.DataFrame(requests.get(rev_url, timeout=40).json())
        return quotes, reports, revenue, latest_date
    except Exception as e:
        print(f"API Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None

def run_valuation():
    print("=== 智能估值系統 (Valuation Screener) ===")
    quotes, reports, revenue, date = fetch_data()
    if quotes.empty or reports.empty: return

    for df in [quotes, reports, revenue]:
        if not df.empty: df['symbol'] = df['symbol'].astype(str)

    reports = reports.sort_values('date').groupby('symbol').last().reset_index()
    revenue = revenue.sort_values('date').groupby('symbol').last().reset_index() if not revenue.empty else pd.DataFrame()

    merged = pd.merge(quotes, reports, on='symbol', how='inner', suffixes=('', '_rpt'))
    if not revenue.empty:
        merged = pd.merge(merged, revenue[['symbol', 'yoy_pct']], on='symbol', how='left')
    else:
        merged['yoy_pct'] = 0

    cols = ['close', 'eps', 'nav_per_share', 'yoy_pct', 'volume']
    for c in cols:
        merged[c] = pd.to_numeric(merged[c], errors='coerce')
    
    df = merged[(merged['eps'] > 0) & (merged['nav_per_share'] > 0) & (merged['volume'] > 200000)].copy()

    # 計算年化數據
    df['annual_eps'] = df['eps'] * 4
    df['roe_annual'] = (df['annual_eps'] / df['nav_per_share']) * 100
    
    # 1. 葛拉漢合理價 (Graham)
    # Sqrt(22.5 * EPS * NAV)
    # 這裡的 EPS 用年化
    df['price_graham'] = np.sqrt(22.5 * df['annual_eps'] * df['nav_per_share'])
    
    # 2. PE 模型
    def get_target_pe(row):
        base = 12
        if row['yoy_pct'] > 50: base = 20
        elif row['yoy_pct'] > 20: base = 15
        elif row['yoy_pct'] < 0: base = 10
        return base
    df['target_pe'] = df.apply(get_target_pe, axis=1)
    df['price_pe'] = df['annual_eps'] * df['target_pe']
    
    # 3. PB 模型
    def get_target_pb(roe):
        if roe > 30: return 4.0
        if roe > 20: return 2.5
        if roe > 15: return 1.8
        return 1.2
    df['target_pb'] = df['roe_annual'].apply(get_target_pb)
    df['price_pb'] = df['nav_per_share'] * df['target_pb']
    
    # 綜合
    df['fair_value'] = (df['price_graham'] + df['price_pe'] + df['price_pb']) / 3
    df['upside'] = (df['fair_value'] - df['close']) / df['close'] * 100
    
    undervalued = df[df['upside'] > 30].sort_values('upside', ascending=False)
    
    print(f"\n基準日: {date}")
    print(f"掃描個股: {len(df)} 檔 (排除虧損與殭屍股)")
    print(f"嚴重低估名單 (>30%空間): {len(undervalued)} 檔")
    
    if not undervalued.empty:
        cols = ['symbol', 'name', 'close', 'fair_value', 'upside', 'roe_annual', 'target_pe']
        print("\n💰 價值投資買進名單 (Top 15):")
        pd.options.display.max_columns = None
        pd.options.display.width = 1000
        print(undervalued[cols].head(15).to_string(index=False))
        
        print("\n[欄位說明]")
        print("- fair_value: 綜合估算合理股價")
        print("- upside: 潛在獲利空間 (%)")
        print("- roe_annual: 預估年化股東權益報酬率")
    else:
        print("無低估標的。")

if __name__ == "__main__":
    run_valuation()