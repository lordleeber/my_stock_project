import os
import pandas as pd
from sqlalchemy import create_engine

def get_db_url():
    """取得資料庫連線字串"""
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def prepare_v1_data():
    """
    準備 V1 版本的特徵資料集
    核心邏輯：利用「Q2 的淨利率」乘以「Q3 的總營收」來推估 Q3 EPS
    """
    engine = create_engine(get_db_url())
    year = 2024
    # 定義查詢的時間標籤
    q2_str, q3_str = f"{year}Q2", f"{year}Q3"
    m7, m8, m9 = f"{year}M07", f"{year}M08", f"{year}M09"
    
    print(f"正在準備 {year}Q3 的 V1 特徵資料...")
    
    # 這裡執行一個大型的跨表 JOIN：
    # 1. q2_data: 從損益表抓取營收、淨利率，並從資產負債表抓取股本 (算 EPS 的分母)
    # 2. q3_rev: 從月營收表加總 7, 8, 9 三個月的實質營收
    # 3. q3_target: 從季報總表抓取「真實的 Q3 EPS」作為機器學習的答案 (Label)
    query = f"""
    WITH q2_data AS (
        SELECT i.symbol, i.name, i.revenue_q as q2_rev, 
               i.net_income_q / NULLIF(i.revenue_q, 0) as q2_margin,
               i.eps_q as q2_eps, b.share_capital as capital
        FROM income_statement i
        JOIN balance_sheet b ON i.symbol = b.symbol AND i.date = b.date
        WHERE i.date = '{q2_str}' AND i.market = 'sii'
    ),
    q3_rev AS (
        SELECT symbol, SUM(revenue_current) as q3_rev_total
        FROM monthly_revenue WHERE date IN ('{m7}', '{m8}', '{m9}') GROUP BY symbol
    ),
    q3_target AS (
        SELECT symbol, eps_q as target_eps FROM quarterly_reports WHERE date = '{q3_str}'
    )
    SELECT q2.*, r.q3_rev_total, t.target_eps
    FROM q2_data q2
    JOIN q3_rev r ON q2.symbol = r.symbol
    JOIN q3_target t ON q2.symbol = t.symbol
    """
    df = pd.read_sql(query, engine)
    
    # 計算一個「簡單公式預測」作為對照組
    # 公式：預估 EPS = (Q3總營收 * Q2淨利率) / (股本 / 10)
    # 註：台灣股票面額通常為 10 元，故股本除以 10 等於總股數
    df['naive_pred_eps'] = (df['q3_rev_total'] * df['q2_margin']) / (df['capital'] / 10)
    return df

if __name__ == "__main__":
    df = prepare_v1_data()
    # 將處理好的特徵存成 CSV，供 train.py 使用
    df.to_csv("analysis/v1/dataset.csv", index=False)
    print(f"V1 資料集已儲存 (共 {len(df)} 筆)。")
