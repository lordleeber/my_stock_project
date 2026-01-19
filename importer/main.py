import os
import time
import glob
import traceback
import polars as pl
from sqlalchemy import create_engine, text

def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def wait_for_db(engine):
    retries = 30
    while retries > 0:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print("Database is ready!")
            return
        except Exception as e:
            print(f"Waiting for database... ({retries} retries left)")
            time.sleep(2)
            retries -= 1
    raise Exception("Database connection failed")

def import_data(engine):
    data_dir = "/app/data/processed"
    
    # 遍歷類別目錄 (如 daily_quotes, institutional_investors)
    categories = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
    
    for category in categories:
        cat_path = os.path.join(data_dir, category)
        # 遍歷日期目錄
        date_dirs = glob.glob(os.path.join(cat_path, "date=*"))
        
        for date_dir in sorted(date_dirs):
            date_str = date_dir.split("=")[1]
            
            # 遍歷 CSV 檔案 (sii.csv, otc.csv)
            csv_files = glob.glob(os.path.join(date_dir, "*.csv"))
            
            for csv_file in csv_files:
                market = os.path.basename(csv_file).split(".")[0] # sii or otc
                table_name = category # 資料表名稱 = 類別名稱
                
                try:
                    print(f"Processing {table_name} - {date_str} - {market}...")
                    
                    # 1. 讀取 CSV
                    # 指定 infer_schema_length=0 避免型別誤判，統一先讀成字串再讓 pandas/sqlalchemy 處理？
                    # 不，這裡我們信任 CSV 已經被處理過，但為了安全，我們可以讓 Polars 自動推斷
                    df = pl.read_csv(csv_file)
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    # 2. 寫入資料庫
                    
                    # 為了避免重複資料，先刪除該日期與市場的舊資料
                    with engine.begin() as conn:
                        table_exists = conn.execute(text(
                            f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
                        )).scalar()
                        
                        if table_exists:
                            delete_query = text(f"DELETE FROM {table_name} WHERE date = :date AND market = :market")
                            conn.execute(delete_query, {"date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}", "market": market})

                    # 3. 使用 Pandas 寫入 (更穩定的錯誤訊息)
                    # chunksize 避免封包過大
                    df.to_pandas().to_sql(
                        name=table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        chunksize=2000 
                    )
                    print(f"  -> Imported {df.height} rows.")

                except Exception as e:
                    print(f"Failed to import {csv_file}")
                    print(traceback.format_exc())

if __name__ == "__main__":
    print("Starting Importer...")
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    wait_for_db(engine)
    import_data(engine)
    print("All imports completed.")
