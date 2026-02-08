import pandas as pd
import requests
import sys

# ---------------------------------------------------------
# 基本面旗艦級選股系統 4.5 (絕對時間軸嚴謹版)
# ---------------------------------------------------------

API_BASE = "http://100.103.191.79:8000"

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fetch_data_snapshot():
    # 模擬時間點：2025-11-17
    SIM_DATE = "2025-11-17"
    
    print(f"正在還原 {SIM_DATE} 當下的資訊環境...")
    try:
        # 1. 2025Q3 財報
        df_q = pd.DataFrame(requests.get(f"{API_BASE}/raw/quarterly-reports?start_date=2025Q3&end_date=2025Q3&limit=3000").json())
        # 2. 現金流量
        df_cf = pd.DataFrame(requests.get(f"{API_BASE}/raw/cash-flows?start_date=2025Q3&end_date=2025Q3&limit=3000").json())
        # 3. 當時的股價 (2025-11-17)
        df_p = pd.DataFrame(requests.get(f"{API_BASE}/raw/daily-quotes?start_date={SIM_DATE}&end_date={SIM_DATE}&limit=5000").json())
        
        # 4. 當時能看到的最新 3 個月營收 (8, 9, 10月)
        # 11月營收要到 12/10 才公佈，所以當時看不到
        rev_months = ["2025-08-01", "2025-09-01", "2025-10-01"]
        all_rev = []
        for m in rev_months:
            print(f"  抓取歷史營收: {m}...")
            r = requests.get(f"{API_BASE}/raw/monthly-revenue?start_date={m}&end_date={m}&limit=3000").json()
            if r: all_rev.extend(r)
            
        df_r = pd.DataFrame(all_rev)
        
        return df_q, df_cf, df_p, df_r, SIM_DATE
    except Exception as e:
        print(f"資料抓取失敗: {e}")
        return [pd.DataFrame()]*4 + [None]

def run_screener():
    print("=== 基本面專家：旗艦級選股系統 4.5 (時間軸嚴謹版) ===")
    df_q, df_cf, df_p, df_r, sim_date = fetch_data_snapshot()
    
    if df_q.empty or df_p.empty or df_r.empty:
        print("資料不足。")
        return

    # 1. 計算當時可見的營收趨勢 (8, 9, 10月)
    df_r['symbol'] = df_r['symbol'].astype(str)
    df_r['yoy_pct'] = pd.to_numeric(df_r['yoy_pct'], errors='coerce')
    df_r = df_r.dropna(subset=['yoy_pct'])
    
    # 確保只用這三個月算平均
    df_r = df_r.sort_values(['symbol', 'date'])
    # 對每檔股票，只取最後 3 筆 (理論上就是 8, 9, 10)
    rev_trend = df_r.groupby('symbol').tail(3).groupby('symbol').agg({
        'yoy_pct': ['mean', 'last'], # last 就是 10月 YoY
        'date': 'count' # 確認是否真的有 3 個月資料
    }).reset_index()
    
    # 欄位扁平化
    rev_trend.columns = ['symbol', 'rev_avg_3m', 'rev_oct_yoy', 'rev_count']
    # 只保留資料完整的股票 (有3個月營收)
    rev_trend = rev_trend[rev_trend['rev_count'] == 3]

    # 2. 合併
    for df in [df_q, df_cf, df_p]: df['symbol'] = df['symbol'].astype(str)
    
    df = pd.merge(df_q, df_cf[['symbol', 'cash_flow_operating']], on='symbol', how='inner')
    df = pd.merge(df, df_p[['symbol', 'close', 'pe_ratio', 'volume']], on='symbol', how='inner')
    df = pd.merge(df, rev_trend, on='symbol', how='inner')

    # 3. 指標計算
    num_cols = ['revenue', 'op_income', 'net_income', 'eps_yoy', 'equity_to_assets_ratio', 'pe_ratio', 'rev_avg_3m', 'rev_oct_yoy', 'cash_flow_operating']
    for c in num_cols: df[c] = pd.to_numeric(df[c], errors='coerce')

    df['op_margin'] = (df['op_income'] / df['revenue']) * 100
    df['cash_quality'] = df['cash_flow_operating'] / df['net_income']

    # --- 歷史模擬篩選邏輯 ---
    # 在 11/17 財報公佈當下，我們會選誰？
    # 1. 營收動能: 8-10月平均成長 > 10% 且 10月營收持續成長 (>0)
    # 2. 財報爆發: Q3 EPS YoY > 20%
    # 3. 獲利品質: 營益率 > 10%, 含金量 > 0.8
    # 4. 安全便宜: 權益比 > 40%, 當時 PE < 18 (考量當時可能已漲一段，稍微放寬 PE)
    
    mask = (df['rev_avg_3m'] > 10) & (df['rev_oct_yoy'] > 0) & \
           (df['eps_yoy'] > 20) & \
           (df['op_margin'] > 10) & \
           (df['cash_quality'] > 0.8) & \
           (df['equity_to_assets_ratio'] > 40) & \
           (df['pe_ratio'] < 18) & (df['pe_ratio'] > 0) & \
           (df['volume'] >= 300000)
    
    candidates = df[mask].copy()
    
    # 評分
    candidates['master_score'] = (candidates['rev_avg_3m'] * 0.4) + (candidates['eps_yoy'] * 0.3) + (candidates['op_margin'] * 0.3)
    candidates = candidates.sort_values('master_score', ascending=False)

    print(f"\n模擬決策日：{sim_date}")
    print(f"當時符合「財報優 + Q4開局動能強」嚴選個股：{len(candidates)} 檔")
    
    if not candidates.empty:
        show_cols = ['symbol', 'name', 'close', 'pe_ratio', 'rev_avg_3m', 'rev_oct_yoy', 'eps_yoy', 'op_margin']
        print("\n💎 2025年11月 專家真實推薦名單 (Top 10):")
        pd.options.display.max_columns = None
        pd.options.display.width = 1000
        print(candidates[show_cols].head(10).to_string(index=False))
    else:
        print("\n模擬當時無符合高標準標的。")

if __name__ == "__main__":
    run_screener()