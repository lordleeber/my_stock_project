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

def prepare_v2_data():
    """
    準備 V2 版本的特徵資料集
    核心邏輯：加入「去年同期財報」與「月營收 YoY」
    這能讓模型學習到：如果去年 Q3 比 Q2 強，那麼今年可能也有同樣的季節性趨勢
    """
    engine = create_engine(get_db_url())
    all_data = []
    
    # 遍歷 2021-2024 年，建立跨年度的訓練集
    for year in range(2021, 2025):
        # 定義當前年度與去年同期的查詢標籤
        q2_str, q3_str, ly_q3_str = f"{year}Q2", f"{year}Q3", f"{year-1}Q3"
        m7, m8, m9 = f"{year}M07", f"{year}M08", f"{year}M09"
        ly_m7 = f"{year-1}M07"
        
        print(f"正在準備 {year} 年資料 (包含自 {year-1} 年起的季節性因子)...")
        
        # 這裡執行一個非常複雜的 SQL：
        # 1. q2_data: 取得今年的 Q2 表現
        # 2. ly_data: 取得「去年 Q3」的真實 EPS (這是預測今年 Q3 重要的參考點)
        # 3. this_rev / last_rev: 取得今年 7 月與去年 7 月營收，用以計算 YoY
        query = f"""
        WITH q2_data AS (
            SELECT symbol, name, eps_q as q2_eps, revenue_q as q2_rev,
                   net_income_q / NULLIF(revenue_q, 0) as q2_margin
            FROM income_statement WHERE date = '{q2_str}' AND market = 'sii'
        ),
        ly_data AS (
            SELECT symbol, eps_q as ly_q3_eps FROM quarterly_reports WHERE date = '{ly_q3_str}'
        ),
        this_rev AS (
            SELECT symbol, 
                   MAX(CASE WHEN date='{m7}' THEN revenue_current END) as rev_m7,
                   MAX(CASE WHEN date='{m8}' THEN revenue_current END) as rev_m8,
                   MAX(CASE WHEN date='{m9}' THEN revenue_current END) as rev_m9
            FROM monthly_revenue WHERE date IN ('{m7}','{m8}','{m9}') GROUP BY symbol
        ),
        last_rev AS (
            SELECT symbol, 
                   MAX(CASE WHEN date='{ly_m7}' THEN revenue_current END) as ly_rev_m7
            FROM monthly_revenue WHERE date = '{ly_m7}' GROUP BY symbol
        ),
        target AS (
            SELECT symbol, eps_q as target_eps FROM quarterly_reports WHERE date = '{q3_str}'
        )
        SELECT '{year}' as year, q.*, ly.ly_q3_eps, t.target_eps,
               m.rev_m7, m.rev_m8, m.rev_m9, (m.rev_m7/NULLIF(lm.ly_rev_m7,0)-1) as rev_yoy_m7
        FROM q2_data q
        JOIN ly_data ly ON q.symbol = ly.symbol
        JOIN this_rev m ON q.symbol = m.symbol
        JOIN last_rev lm ON q.symbol = lm.symbol
        JOIN target t ON q.symbol = t.symbol
        """
        all_data.append(pd.read_sql(query, engine))
    
    # 將所有年份的資料垂直合併成一個大型訓練集
    df = pd.concat(all_data)
    return df

if __name__ == "__main__":
    df = prepare_v2_data()
    df.to_csv("analysis/v2/dataset.csv", index=False)
    print(f"V2 資料集已儲存 (共 {len(df)} 筆樣本)。")
