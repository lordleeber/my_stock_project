import os
import time
import glob
import traceback
import datetime
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

def get_filter_dates():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    # 這裡的 DEBUG 訊息非常重要
    print(f"DEBUG: START_DATE from env: {start_env}")
    print(f"DEBUG: END_DATE from env: {end_env}")
    
    start_date = datetime.datetime.strptime(start_env, "%Y%m%d") if (start_env and start_env.strip()) else None
    end_date = datetime.datetime.strptime(end_env, "%Y%m%d") if (end_env and end_env.strip()) else None
    return start_date, end_date

def import_data(engine):
    data_dir = "/app/data/processed"
    start_date, end_date = get_filter_dates()
    
    if start_date: print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")
    if end_date: print(f"Filter End Date: {end_date.strftime('%Y-%m-%d')}")

    # 遍歷類別目錄
    categories = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]
    
    for category in categories:
        cat_path = os.path.join(data_dir, category)
        date_dirs = glob.glob(os.path.join(cat_path, "date=*"))
        
        for date_dir in sorted(date_dirs):
            date_str = date_dir.split("=")[1]
            
            # 日期篩選邏輯
            try:
                current_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                if start_date and current_date < start_date:
                    continue
                if end_date and current_date > end_date:
                    continue
            except ValueError:
                continue

            # 遍歷 CSV 檔案
            csv_files = glob.glob(os.path.join(date_dir, "*.csv"))
            for csv_file in csv_files:
                market = os.path.basename(csv_file).split(".")[0] # sii or otc
                table_name = category # 資料表名稱 = 類別名稱
                
                try:
                    print(f"Processing {table_name} - {date_str} - {market}...")
                    
                    df = pl.read_csv(csv_file)
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    # 為了避免重複資料，先刪除該日期與市場的舊資料
                    with engine.begin() as conn:
                        table_exists = conn.execute(text(
                            f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
                        )).scalar()
                        
                        if table_exists:
                            delete_query = text(f"DELETE FROM {table_name} WHERE date = :date AND market = :market")
                            conn.execute(delete_query, {"date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}", "market": market})

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