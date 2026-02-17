import os
import datetime
import pandas as pd
from sqlalchemy import create_engine, text

def get_db_url():
    """取得資料庫連線字串"""
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def save_eps_predictions(df, target_quarter, model_version):
    """
    通用函式：將 EPS 預測結果存入資料庫
    
    Args:
        df: 包含 ['symbol', 'predict_eps'] 的 DataFrame
        target_quarter: 目標季度，例如 '2024Q3'
        model_version: 模型版本，例如 'v4'
    """
    engine = create_engine(get_db_url())
    
    # 1. 準備資料
    predict_df = df[['symbol', 'predict_eps']].copy()
    predict_df['symbol'] = predict_df['symbol'].astype(str)
    predict_df['target_quarter'] = target_quarter
    predict_df['model_version'] = model_version
    predict_df['created_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"正在將 {target_quarter} 的預測結果 ({model_version}) 存入資料庫...")
    
    try:
        with engine.connect() as conn:
            # 2. 檢查表格是否存在，存在才執行刪除
            check_table_sql = text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'eps_predictions')")
            table_exists = conn.execute(check_table_sql).scalar()
            
            if table_exists:
                delete_sql = text("DELETE FROM eps_predictions WHERE target_quarter = :q AND model_version = :v")
                conn.execute(delete_sql, {"q": target_quarter, "v": model_version})
                conn.commit()
            
            # 3. 執行批次寫入 (to_sql 會在表格不存在時自動建立)
            predict_df.to_sql('eps_predictions', engine, if_exists='append', index=False, chunksize=1000)
            
        print(f"✅ 成功存入 {len(predict_df)} 筆預測資料。")
        return True
    except Exception as e:
        print(f"❌ 存入預測資料失敗: {e}")
        return False
