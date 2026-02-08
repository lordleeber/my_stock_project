import pandas as pd
import requests
import sys

# ---------------------------------------------------------
# 基本面選股回測報告 (修正 Name 缺失問題)
# ---------------------------------------------------------

API_BASE = "http://100.103.191.79:8000"

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fetch_data_at_date(date):
    try:
        url = f"{API_BASE}/raw/daily-quotes?start_date={date}&end_date={date}&limit=5000"
        resp = requests.get(url, timeout=40)
        return pd.DataFrame(resp.json())
    except:
        return pd.DataFrame()

def run_backtest():
    BUY_DATE = "2025-11-17"
    CURRENT_DATE = "2026-02-06"
    
    print(f"=== 基本面策略回測：{BUY_DATE} -> {CURRENT_DATE} ===")
    
    try:
        df_q = pd.DataFrame(requests.get(f"{API_BASE}/raw/quarterly-reports?start_date=2025Q3&end_date=2025Q3&limit=3000").json())
        df_r = pd.DataFrame(requests.get(f"{API_BASE}/raw/monthly-revenue?start_date=2025-10-01&end_date=2025-10-01&limit=3000").json())
        df_p_buy = fetch_data_at_date(BUY_DATE)
        df_p_now = fetch_data_at_date(CURRENT_DATE)
    except:
        print("資料獲取失敗。")
        return

    if df_q.empty or df_p_buy.empty or df_p_now.empty:
        print("回測所需資料不足。")
        return

    for d in [df_q, df_r, df_p_buy, df_p_now]: d['symbol'] = d['symbol'].astype(str)
    
    # 預先處理 df_p_buy 取得名字
    df = pd.merge(df_q, df_p_buy[['symbol', 'name', 'close', 'pe_ratio', 'volume']], on='symbol', how='inner')
    df = pd.merge(df, df_r[['symbol', 'yoy_pct']], on='symbol', how='inner')
    
    # 數值轉換
    for c in ['eps_yoy', 'yoy_pct', 'op_income', 'revenue', 'pe_ratio', 'volume', 'close']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    
    df['op_margin'] = (df['op_income'] / df['revenue']) * 100
    
    mask = (df['eps_yoy'] > 15) & \
           (df['yoy_pct'] > 0) & \
           (df['op_margin'] > 10) & \
           (df['pe_ratio'] < 18) & \
           (df['pe_ratio'] > 0) & \
           (df['volume'] >= 300000)
    
    candidates = df[mask].copy()
    candidates = candidates.rename(columns={'close': 'buy_price'})
    
    # 3. 獲取現在價格
    final = pd.merge(candidates, df_p_now[['symbol', 'close']], on='symbol', how='inner')
    final = final.rename(columns={'close': 'current_price'})
    
    final['return_pct'] = (final['current_price'] - final['buy_price']) / final['buy_price'] * 100
    final = final.sort_values('return_pct', ascending=False)

    print(f"\n成功追蹤 {len(final)} 檔標的之表現：")
    
    # 檢查並修正 show_cols
    available_cols = final.columns.tolist()
    show_cols = ['symbol', 'name', 'buy_price', 'current_price', 'return_pct', 'pe_ratio', 'eps_yoy']
    show_cols = [c for c in show_cols if c in available_cols]
    
    pd.options.display.max_columns = None
    pd.options.display.width = 1000
    print(final[show_cols].to_string(index=False))
    
    if len(final) > 0:
        avg_return = final['return_pct'].mean()
        win_rate = (final['return_pct'] > 0).sum() / len(final) * 100
        print(f"\n--- 回測總結 (經過約 80 天) ---")
        print(f"平均報酬率: {avg_return:.2f}%")
        print(f"勝率: {win_rate:.2f}%")
        print(f"表現最好: {final.iloc[0]['name'] if 'name' in final.columns else 'N/A'} ({final.iloc[0]['return_pct']:.2f}%)")
        print(f"表現最差: {final.iloc[-1]['name'] if 'name' in final.columns else 'N/A'} ({final.iloc[-1]['return_pct']:.2f}%)")

if __name__ == "__main__":
    run_backtest()
