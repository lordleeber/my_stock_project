import os
import pandas as pd
from sqlalchemy import create_engine, text

def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def prepare_v3_data():
    engine = create_engine(get_db_url())
    
    all_years_data = []
    # 抓取 2021-2024 的資料
    for year in range(2021, 2025):
        q2_str, q3_str = f"{year}Q2", f"{year}Q3"
        ly_q3_str = f"{year-1}Q3"
        m7, m8, m9 = f"{year}M07", f"{year}M08", f"{year}M09"
        
        print(f"Processing Year {year} for V3 Analysis (OCF + Net Income + Monthly)...")
        
        query = f"""
        WITH 
        q2_fundamental AS (
            SELECT 
                i.symbol, i.name,
                i.revenue_q as q2_rev, 
                i.net_income_q as q2_ni,
                i.net_income_q / NULLIF(i.revenue_q, 0) as q2_margin,
                i.eps_q as q2_eps,
                b.share_capital as capital,
                b.retained_earnings as q2_retained_earnings,
                c.cash_flow_operating_q as q2_ocf
            FROM income_statement i
            JOIN balance_sheet b ON i.symbol = b.symbol AND i.date = b.date
            JOIN cash_flow c ON i.symbol = c.symbol AND i.date = c.date
            WHERE i.date = '{q2_str}' AND i.market = 'sii'
        ),
        this_monthly AS (
            SELECT symbol,
                MAX(CASE WHEN date = '{m7}' THEN revenue_current END) as rev_m7,
                MAX(CASE WHEN date = '{m8}' THEN revenue_current END) as rev_m8,
                MAX(CASE WHEN date = '{m9}' THEN revenue_current END) as rev_m9
            FROM monthly_revenue WHERE date IN ('{m7}', '{m8}', '{m9}') GROUP BY symbol
        ),
        target_q3 AS (
            SELECT symbol, eps_q as target_eps,
                (SELECT eps_q FROM quarterly_reports qly WHERE qly.symbol = qr.symbol AND qly.date = '{ly_q3_str}') as ly_q3_eps
            FROM quarterly_reports qr WHERE date = '{q3_str}'
        )
        SELECT 
            '{year}' as year, f.*, 
            m.rev_m7, m.rev_m8, m.rev_m9,
            t.ly_q3_eps, t.target_eps
        FROM q2_fundamental f
        JOIN this_monthly m ON f.symbol = m.symbol
        JOIN target_q3 t ON f.symbol = t.symbol
        """
        df_year = pd.read_sql(query, engine)
        if not df_year.empty:
            all_years_data.append(df_year)

    final_df = pd.concat(all_years_data)
    final_df = final_df.dropna(subset=['q2_ni', 'q2_ocf', 'target_eps'])
    
    # 衍生特徵：三位一體
    final_df['q2_ocf_ratio'] = (final_df['q2_ocf'] / NULLIF_PD(final_df['q2_ni'])).clip(-5, 5) # 獲利含金量
    final_df['q2_re_ratio'] = final_df['q2_retained_earnings'] / NULLIF_PD(final_df['capital']) # 保留盈餘比
    
    # 月趨勢
    final_df['rev_trend_m8_m7'] = (final_df['rev_m8'] / NULLIF_PD(final_df['rev_m7'])) - 1
    final_df['rev_trend_m9_m8'] = (final_df['rev_m9'] / NULLIF_PD(final_df['rev_m8'])) - 1

    print(f"V3 dataset prepared: {len(final_df)} samples.")
    return final_df

def NULLIF_PD(series):
    return series.replace(0, pd.NA)

if __name__ == "__main__":
    df = prepare_v3_data()
    df.to_csv("analysis/eps_v3_dataset.csv", index=False)
    print("Saved to analysis/eps_v3_dataset.csv")
