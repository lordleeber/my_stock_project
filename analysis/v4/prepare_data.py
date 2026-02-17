import os
import pandas as pd
from sqlalchemy import create_engine, text
import argparse
from pathlib import Path

def get_db_url():
    """取得資料庫連線字串"""
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def prepare_v4_data(start_year, end_year):
    """
    準備 V4 (財務比率全整合) 特徵資料集
    核心邏輯：整合四大報表，計算關鍵財務比率
    """
    engine = create_engine(get_db_url())
    all_years_data = []
    
    # 遍歷指定年份區間
    for year in range(start_year, end_year + 1):
        q1_str, q2_str, q3_str = f"{year}Q1", f"{year}Q2", f"{year}Q3"
        ly_q3_str = f"{year-1}Q3"
        m7, m8, m9 = f"{year}M07", f"{year}M08", f"{year}M09"
        
        print(f"正在準備 {year} 年 V4 財務比率特徵資料...")
        
        # 使用 CTE 結構確保 SQL 邏輯清晰 (Reviewer 肯定點)
        query = f"""
        WITH 
        q2_data AS (
            SELECT 
                i.symbol, i.name,
                i.revenue_q as q2_rev, 
                i.net_income_q as q2_ni,
                i.eps_q as q2_eps,
                -- 獲利三率
                i.gross_profit_q / NULLIF(i.revenue_q, 0) as q2_gross_margin,
                i.operating_income_q / NULLIF(i.revenue_q, 0) as q2_operating_margin,
                i.net_income_q / NULLIF(i.revenue_q, 0) as q2_net_margin,
                -- 獲利純度
                i.non_operating_income_q / NULLIF(i.pretax_income_q, 0) as q2_non_op_ratio,
                -- 財務結構
                b.total_liabilities / NULLIF(b.total_assets, 0) as q2_debt_ratio,
                b.current_assets / NULLIF(b.current_liabilities, 0) as q2_current_ratio,
                b.share_capital as capital,
                b.retained_earnings as q2_retained_earnings,
                -- 效率指標
                i.net_income_q / NULLIF(b.total_equity, 0) as q2_roe,
                i.net_income_q / NULLIF(b.total_assets, 0) as q2_roa,
                -- 現金流
                c.cash_flow_operating_q as q2_ocf,
                ABS(c.cash_flow_investing_q) / NULLIF(i.revenue_q, 0) as q2_capex_intensity
            FROM income_statement i
            JOIN balance_sheet b ON i.symbol = b.symbol AND i.date = b.date
            JOIN cash_flow c ON i.symbol = c.symbol AND i.date = c.date
            WHERE i.date = '{q2_str}' AND i.market = 'sii'
        ),
        q1_data AS (
            SELECT symbol, 
                   net_income_q / NULLIF(revenue_q, 0) as q1_net_margin
            FROM income_statement WHERE date = '{q1_str}'
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
            '{year}' as year, f.*, q1.q1_net_margin,
            m.rev_m7, m.rev_m8, m.rev_m9,
            t.ly_q3_eps, t.target_eps
        FROM q2_data f
        LEFT JOIN q1_data q1 ON f.symbol = q1.symbol
        JOIN this_monthly m ON f.symbol = m.symbol
        JOIN target_q3 t ON f.symbol = t.symbol
        """
        
        df_year = pd.read_sql(query, engine)
        if not df_year.empty:
            all_years_data.append(df_year)

    if not all_years_data:
        return pd.DataFrame()

    final_df = pd.concat(all_years_data)
    final_df = final_df.dropna(subset=['q2_ni', 'target_eps'])
    
    # 衍生特徵計算
    final_df['q2_ocf_ratio'] = (final_df['q2_ocf'] / final_df['q2_ni'].replace(0, 1e-9)).clip(-5, 5)
    final_df['margin_momentum'] = final_df['q2_net_margin'] - final_df['q1_net_margin'].fillna(final_df['q2_net_margin'])
    final_df['rev_trend_m8_m7'] = (final_df['rev_m8'] / final_df['rev_m7'].replace(0, 1e-9)) - 1
    final_df['rev_trend_m9_m8'] = (final_df['rev_m9'] / final_df['rev_m8'].replace(0, 1e-9)) - 1

    return final_df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V4 資料準備腳本 (參數化版本)")
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=2024)
    parser.add_argument("--output", type=str, default="analysis/v4/dataset.csv")
    args = parser.parse_args()

    df = prepare_v4_data(args.start_year, args.end_year)
    
    if not df.empty:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        df.to_csv(args.output, index=False)
        print(f"✅ V4 資料集已儲存至 {args.output} (共 {len(df)} 筆樣本)")
    else:
        print("❌ 未找到符合條件的資料")
