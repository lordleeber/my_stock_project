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

    # 類別過濾：支援只導入特定類型的數據
    import_category = os.getenv("IMPORT_CATEGORY")
    if import_category:
        print(f"Import Category Filter: {import_category}")
        categories = [import_category] if import_category in os.listdir(data_dir) else []
        if not categories:
            print(f"Warning: Category '{import_category}' not found in {data_dir}")
            return
    else:
        # 遍歷類別目錄
        categories = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]

    for category in categories:
        cat_path = os.path.join(data_dir, category)
        
        # --- 特別處理 revenue (月營收) ---
        if category == "revenue":
            # 目錄結構: revenue/YYYY-MM/revenue_YYYYMM.csv
            subdirs = sorted([d for d in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, d))])
            
            for subdir in subdirs: # subdir is YYYY-MM
                if len(subdir) != 7: continue
                
                # 日期篩選 (以月份的第一天為準)
                try:
                    month_date = datetime.datetime.strptime(f"{subdir}-01", "%Y-%m-%d")
                    # 如果有設定 start_date，且該月份 < start_date 的月份 (忽略日)，則跳過
                    # 比較邏輯：
                    # start_date: 20250515 -> start_month: 20250501
                    if start_date:
                        start_month = start_date.replace(day=1)
                        if month_date < start_month: continue
                    if end_date:
                        end_month = end_date.replace(day=1)
                        if month_date > end_month: continue
                except ValueError:
                    continue
                
                csv_files = glob.glob(os.path.join(cat_path, subdir, "*.csv"))
                for csv_file in csv_files:
                    table_name = "monthly_revenue"
                    try:
                        print(f"Processing {table_name} - {subdir}...")
                        df = pl.read_csv(csv_file)
                        if df.height == 0:
                            print("  -> Empty file, skipping.")
                            continue

                        # 過濾 ETF：排除 symbol 以 "00" 開頭的記錄
                        if "symbol" in df.columns:
                            original_count = df.height
                            df = df.filter(~pl.col("symbol").cast(pl.Utf8).str.starts_with("00"))
                            filtered_count = original_count - df.height
                            if filtered_count > 0:
                                print(f"  -> Filtered out {filtered_count} ETF records")

                            if df.height == 0:
                                print("  -> No data after filtering ETFs, skipping.")
                                continue

                        # Delete-before-Insert
                        with engine.begin() as conn:
                            # 檢查 table 是否存在
                            table_exists = conn.execute(text(
                                f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
                            )).scalar()

                            if table_exists:
                                # 刪除該月份的所有資料 (因為 CSV 包含 sii + otc)
                                # CSV 內的 date 欄位格式為 YYYY-MM-01
                                target_date = f"{subdir}-01"
                                conn.execute(text(f"DELETE FROM {table_name} WHERE date = :date"), {"date": target_date})
                        
                        df.to_pandas().to_sql(
                            name=table_name,
                            con=engine,
                            if_exists="append", # Table 不存在時會自動建立
                            index=False,
                            chunksize=2000
                        )
                        print(f"  -> Imported {df.height} rows to {table_name}.")
                        
                    except Exception as e:
                        print(f"Failed to import {csv_file}")
                        print(traceback.format_exc())
            continue

        # --- 特別處理 shareholding_div (集保股權分散表) ---
        if category == "shareholding_div":
            date_dirs = sorted(glob.glob(os.path.join(cat_path, "date=*")))

            for date_dir in date_dirs:
                date_str = date_dir.split("=")[1]

                # 日期篩選
                try:
                    current_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                    if start_date and current_date < start_date:
                        continue
                    if end_date and current_date > end_date:
                        continue
                except ValueError:
                    continue

                csv_file = os.path.join(date_dir, "all.csv")
                if not os.path.exists(csv_file):
                    continue

                table_name = "shareholding_div"
                try:
                    print(f"Processing {table_name} - {date_str}...")

                    df = pl.read_csv(csv_file)
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    # 過濾 ETF
                    if "symbol" in df.columns:
                        original_count = df.height
                        df = df.filter(~pl.col("symbol").cast(pl.Utf8).str.starts_with("00"))
                        filtered_count = original_count - df.height
                        if filtered_count > 0:
                            print(f"  -> Filtered out {filtered_count} ETF records")

                        if df.height == 0:
                            print("  -> No data after filtering ETFs, skipping.")
                            continue

                    # Delete-before-Insert (依日期)
                    with engine.begin() as conn:
                        table_exists = conn.execute(text(
                            f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}')"
                        )).scalar()

                        if table_exists:
                            target_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
                            conn.execute(text(f"DELETE FROM {table_name} WHERE date = :date"), {"date": target_date})

                    df.to_pandas().to_sql(
                        name=table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        chunksize=5000
                    )
                    print(f"  -> Imported {df.height} rows.")

                except Exception as e:
                    print(f"Failed to import {csv_file}")
                    print(traceback.format_exc())
            continue

        # --- 一般處理 (daily_quotes, etc.) ---
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

                    # 過濾 ETF：排除 symbol 以 "00" 開頭的記錄（ETF 沒有基本面數據）
                    if "symbol" in df.columns:
                        original_count = df.height
                        df = df.filter(~pl.col("symbol").cast(pl.Utf8).str.starts_with("00"))
                        filtered_count = original_count - df.height
                        if filtered_count > 0:
                            print(f"  -> Filtered out {filtered_count} ETF records")

                        if df.height == 0:
                            print("  -> No data after filtering ETFs, skipping.")
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