import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime

# 加入專案根目錄到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.http_client import fetch_dataframe, fetch_json
from common.constants import API_BASE

# ---------------------------------------------------------
# 基本面旗艦級估值系統 2.4 (共用模組 + 重試機制)
# ---------------------------------------------------------

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def get_latest_quarter():
    """根據當前日期計算最新可用的財報季度"""
    today = datetime.now()
    year, month = today.year, today.month

    # 財報公告時程：Q1(5/15), Q2(8/14), Q3(11/14), Q4(3/31)
    if month >= 11 and month <= 12:
        return f"{year}Q3"
    elif month >= 8:
        return f"{year}Q2"
    elif month >= 5:
        return f"{year}Q1"
    elif month >= 4:
        return f"{year-1}Q4"
    else:
        return f"{year-1}Q3"

def fetch_all_data():
    try:
        quarter = get_latest_quarter()
        print(f"使用財報季度: {quarter}")

        # 取得最新交易日
        latest_data = fetch_json("/raw/daily-quotes", {"start_date": "2025-01-01", "end_date": "2026-12-31", "limit": 1})
        latest_date = latest_data[0]['date'] if latest_data else None

        is_stmt = fetch_dataframe("/raw/income-statements", {"start_date": quarter, "end_date": quarter, "limit": 3000})
        bs_stmt = fetch_dataframe("/raw/balance-sheets", {"start_date": quarter, "end_date": quarter, "limit": 3000})
        cf_stmt = fetch_dataframe("/raw/cash-flows", {"start_date": quarter, "end_date": quarter, "limit": 3000})
        p_data = fetch_dataframe("/raw/daily-quotes", {"start_date": latest_date, "end_date": latest_date, "limit": 5000})
        info = fetch_dataframe("/raw/stock-info", {"limit": 5000})

        return is_stmt, bs_stmt, cf_stmt, p_data, info, latest_date, quarter
    except Exception as e:
        print(f"資料獲取失敗: {e}")
        return [pd.DataFrame()]*5 + [None, None]

def run_valuation():
    print("=== 基本面專家：旗艦級智能估值系統 2.3 ===")
    df_is, df_bs, df_cf, df_p, df_info, l_date, quarter = fetch_all_data()
    if df_p.empty:
        print("無法取得價格資料")
        return

    for d in [df_is, df_bs, df_cf, df_p, df_info]:
        if not d.empty: d['symbol'] = d['symbol'].astype(str)

    df = pd.merge(df_p[['symbol', 'name', 'close', 'pe_ratio']], df_is[['symbol', 'eps', 'revenue', 'operating_income']], on='symbol', how='inner')
    df = pd.merge(df, df_bs[['symbol', 'nav_per_share', 'total_assets', 'total_equity']], on='symbol', how='inner')
    df = pd.merge(df, df_cf[['symbol', 'cash_flow_operating']], on='symbol', how='inner')
    df = pd.merge(df, df_info[['symbol', 'industry']], on='symbol', how='left')

    num_cols = ['close', 'pe_ratio', 'eps', 'nav_per_share', 'cash_flow_operating', 'total_assets', 'total_equity']
    for c in num_cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

    # 過濾 nav_per_share <= 0 的資料，避免除零錯誤
    df = df[df['nav_per_share'] > 0].copy()

    industry_pe = df[df['pe_ratio'] > 0].groupby('industry')['pe_ratio'].median().to_dict()
    df['pb_ratio'] = df['close'] / df['nav_per_share']
    industry_pb = df[(df['pb_ratio'] > 0) & np.isfinite(df['pb_ratio'])].groupby('industry')['pb_ratio'].median().to_dict()

    df['fair_pe'] = df.apply(lambda r: r['eps'] * 4 * industry_pe.get(r['industry'], 15), axis=1)
    df['fair_pb'] = df.apply(lambda r: r['nav_per_share'] * industry_pb.get(r['industry'], 1.5), axis=1)
    df['price_graham'] = np.sqrt(np.maximum(0, 22.5 * (df['eps']*4) * df['nav_per_share']))

    # 綜合合理價 = 預測價格
    df['predict_price'] = np.round((df['fair_pe'] + df['fair_pb'] + df['price_graham']) / 3, 2)

    # 安全計算 upside 和 roe_annual，避免除零
    df['upside'] = np.where(df['close'] > 0,
                           (df['predict_price'] - df['close']) / df['close'] * 100,
                           np.nan)
    df['roe_annual'] = (df['eps'] * 4 / df['nav_per_share']) * 100
    
    undervalued = df[(df['upside'] > 30) & (df['roe_annual'] > 10) & (df['eps'] > 0)].copy()
    undervalued = undervalued.sort_values('upside', ascending=False)
    undervalued['price_date'] = l_date
    undervalued['report_quarter'] = quarter
    undervalued = undervalued.rename(columns={'close': 'market_price'})

    # 欄位順序：price_date, market_price, predict_price
    final_cols = [
        'symbol', 'name', 'industry', 'price_date', 'market_price', 'predict_price',
        'upside', 'pe_ratio', 'eps', 'nav_per_share', 'roe_annual', 'report_quarter'
    ]

    output_path = os.path.join("strategy", "fundamental", "undervalued_picks.csv")
    undervalued[final_cols].to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"完成！共篩選出 {len(undervalued)} 檔低估股票")
    print(f"使用季度: {quarter}, 價格日期: {l_date}")
    print(f"結果見 {output_path}")

if __name__ == "__main__":
    run_valuation()