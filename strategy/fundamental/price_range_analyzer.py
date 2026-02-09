import pandas as pd
import sys
import numpy as np
import os

# 加入專案根目錄到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.http_client import fetch_dataframe, fetch_json
from common.constants import API_BASE

# ---------------------------------------------------------
# 基本面區間價格分析器 2.0 (共用模組 + 重試機制)
# ---------------------------------------------------------

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def fetch_range_quotes(start_date, end_date):
    """
    批次抓取日期區間內的行情資料
    改用日期區間一次查詢，大幅提升效能
    """
    print(f"正在抓取 {start_date} ~ {end_date} 區間行情...")
    try:
        # 嘗試一次抓取整個區間 (需要後端 API 支援)
        df = fetch_dataframe("/raw/daily-quotes", {
            "start_date": start_date,
            "end_date": end_date,
            "limit": 500000  # 增加 limit 以涵蓋所有資料
        })
        if not df.empty:
            print(f"  成功取得 {len(df)} 筆資料")
            return df
    except Exception as e:
        print(f"  批次查詢失敗，改用逐日查詢: {e}")

    # 備援：逐日查詢
    all_quotes = []
    current = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    while current <= end_dt:
        d_str = current.strftime("%Y-%m-%d")
        df = fetch_dataframe("/raw/daily-quotes", {"start_date": d_str, "end_date": d_str, "limit": 5000})
        if not df.empty:
            all_quotes.append(df)
        current += pd.Timedelta(days=1)

    if all_quotes:
        return pd.concat(all_quotes, ignore_index=True)
    return pd.DataFrame()

def run_range_analysis():
    START_DATE = "2025-04-28"
    END_DATE = "2025-06-27"
    print(f"=== 價格波動分析 (格式優化: 小數二位) ===")
    
    report_path = "strategy/fundamental/fundamental_report_2024Q4.csv"
    if not os.path.exists(report_path): return
    
    df_report = pd.read_csv(report_path)
    df_report['symbol'] = df_report['symbol'].astype(str)
    
    df_quotes = fetch_range_quotes(START_DATE, END_DATE)
    if df_quotes.empty: return
    
    df_quotes['symbol'] = df_quotes['symbol'].astype(str)
    for c in ['high', 'low', 'close']:
        df_quotes[c] = pd.to_numeric(df_quotes[c], errors='coerce')

    stats = df_quotes.groupby('symbol').agg({'high': 'max', 'low': 'min'}).reset_index()
    stats.columns = ['symbol', 'period_high', 'period_low']

    result = pd.merge(df_report, stats, on='symbol', how='inner')
    
    # 計算漲跌幅
    result['max_upside_pct'] = (result['period_high'] - result['market_price']) / result['market_price'] * 100
    result['max_drawdown_pct'] = (result['period_low'] - result['market_price']) / result['market_price'] * 100
    
    # --- 格式化：所有浮點數取到小數第二位 ---
    float_cols = result.select_dtypes(include=[np.float64, np.float32]).columns
    result[float_cols] = result[float_cols].round(2)

    # 欄位順序調整
    final_cols = [
        'symbol', 'name', 'industry', 'price_date', 'market_price', 'predict_price',
        'period_high', 'period_low', 'max_upside_pct', 'max_drawdown_pct', 'total_score'
    ]
    
    # 確保只輸出您要求的這些欄位，並排序
    result = result[final_cols].sort_values('total_score', ascending=False)

    output_path = os.path.join("strategy", "fundamental", "price_analysis_2024Q4_2025Q1.csv")
    result.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    print(f"分析完成！所有數值已四捨五入至小數二位。")
    print(f"檔案已更新: {output_path}")

if __name__ == "__main__":
    run_range_analysis()
