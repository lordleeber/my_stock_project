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
    print(f"DEBUG: START_DATE from env: {start_env}")
    print(f"DEBUG: END_DATE from env: {end_env}")

    def parse_date(date_str):
        if not date_str or not date_str.strip():
            return None
        # 嘗試 YYYYMMDD
        try:
            return datetime.datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            pass
        
        # 嘗試 YYYYQX
        try:
            if 'Q' in date_str and len(date_str) == 6:
                year = int(date_str[:4])
                q = int(date_str[5])
                # 轉為該季最後一天的日期物件供過濾比較
                return datetime.datetime(year, q * 3, 28) # 28號保證月份合法
        except Exception:
            pass
            
        return None

    start_date = parse_date(start_env)
    end_date = parse_date(end_env)
    return start_date, end_date

def table_exists(engine, table_name):
    """檢查 table 是否存在"""
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"
        ), {"name": table_name}).scalar()

def date_exists_in_db(engine, table_name, target_date, market=None):
    """
    檢查該日期（及市場）的資料是否已存在於 DB 中。
    用於 skip 已匯入的資料，避免不必要的刪除與重新寫入。
    """
    if not table_exists(engine, table_name):
        return False

    with engine.connect() as conn:
        if market:
            result = conn.execute(
                text(f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE date = :date AND market = :market)"),
                {"date": target_date, "market": market}
            ).scalar()
        else:
            result = conn.execute(
                text(f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE date = :date)"),
                {"date": target_date}
            ).scalar()
    return result

def delete_by_date(engine, table_name, target_date, market=None):
    """刪除指定日期（及市場）的資料"""
    with engine.begin() as conn:
        if market:
            conn.execute(
                text(f"DELETE FROM {table_name} WHERE date = :date AND market = :market"),
                {"date": target_date, "market": market}
            )
        else:
            conn.execute(
                text(f"DELETE FROM {table_name} WHERE date = :date"),
                {"date": target_date}
            )

def filter_etf(df):
    """過濾 ETF（代號以 '00' 開頭）及特別股（代號含英文字母，如 1101B）"""
    if "symbol" not in df.columns:
        return df

    original_count = df.height
    symbol_col = pl.col("symbol").cast(pl.Utf8)
    df = df.filter(
        ~symbol_col.str.starts_with("00") &
        ~symbol_col.str.contains(r"[A-Za-z]")
    )
    filtered_count = original_count - df.height
    if filtered_count > 0:
        print(f"  -> Filtered out {filtered_count} ETF/preferred stock records")
    return df

def import_data(engine):
    data_dir = "/app/data/processed"
    start_date, end_date = get_filter_dates()
    force_reimport = os.getenv("FORCE_REIMPORT", "").lower() in ("1", "true", "yes")

    if start_date: print(f"Filter Start Date: {start_date.strftime('%Y-%m-%d')}")
    if end_date: print(f"Filter End Date: {end_date.strftime('%Y-%m-%d')}")
    if force_reimport: print("FORCE_REIMPORT: enabled (will delete and re-import existing data)")

    # 類別過濾
    import_category = os.getenv("IMPORT_CATEGORY")
    if import_category:
        print(f"Import Category Filter: {import_category}")
        categories = [import_category] if import_category in os.listdir(data_dir) else []
        if not categories:
            print(f"Warning: Category '{import_category}' not found in {data_dir}")
            return
    else:
        categories = [d for d in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, d))]

    for category in categories:
        cat_path = os.path.join(data_dir, category)

        # --- 特別處理 monthly_revenue (月營收) ---
        if category == "monthly_revenue":
            subdirs = sorted([d for d in os.listdir(cat_path) if os.path.isdir(os.path.join(cat_path, d))])

            for subdir in subdirs:
                if len(subdir) != 7: continue

                try:
                    month_date = datetime.datetime.strptime(f"{subdir}-01", "%Y-%m-%d")
                    if start_date:
                        if month_date < start_date.replace(day=1): continue
                    if end_date:
                        if month_date > end_date.replace(day=1): continue
                except ValueError:
                    continue

                csv_files = glob.glob(os.path.join(cat_path, subdir, "*.csv"))
                for csv_file in csv_files:
                    table_name = "monthly_revenue"
                    try:
                        target_date = f"{subdir}-01"

                        # 檢查是否已存在
                        if not force_reimport and date_exists_in_db(engine, table_name, target_date):
                            print(f"Skipping {table_name} - {subdir} (already in DB)")
                            continue

                        print(f"Processing {table_name} - {subdir}...")
                        df = pl.read_csv(csv_file)
                        if df.height == 0:
                            print("  -> Empty file, skipping.")
                            continue

                        df = filter_etf(df)
                        if df.height == 0:
                            print("  -> No data after filtering ETFs, skipping.")
                            continue

                        # 強制重新匯入時先刪除
                        if force_reimport:
                            delete_by_date(engine, table_name, target_date)

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
            continue

        # --- 特別處理 shareholding_div (集保股權分散表) ---
        if category == "shareholding_div":
            date_dirs = sorted(glob.glob(os.path.join(cat_path, "date=*")))

            for date_dir in date_dirs:
                date_str = date_dir.split("=")[1]

                try:
                    current_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                    if start_date and current_date < start_date: continue
                    if end_date and current_date > end_date: continue
                except ValueError:
                    continue

                csv_file = os.path.join(date_dir, "all.csv")
                if not os.path.exists(csv_file): continue

                table_name = "shareholding_div"
                try:
                    target_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

                    if not force_reimport and date_exists_in_db(engine, table_name, target_date):
                        print(f"Skipping {table_name} - {date_str} (already in DB)")
                        continue

                    print(f"Processing {table_name} - {date_str}...")
                    df = pl.read_csv(csv_file, schema_overrides={"symbol": pl.Utf8})
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    df = filter_etf(df)
                    if df.height == 0:
                        print("  -> No data after filtering ETFs, skipping.")
                        continue

                    if force_reimport:
                        delete_by_date(engine, table_name, target_date)

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

        # --- 特別處理 institutional_summary (三大法人買賣超彙總) ---
        if category == "institutional_summary":
            date_dirs = sorted(glob.glob(os.path.join(cat_path, "date=*")))

            for date_dir in date_dirs:
                date_str = date_dir.split("=")[1]

                try:
                    current_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                    if start_date and current_date < start_date: continue
                    if end_date and current_date > end_date: continue
                except ValueError:
                    continue

                csv_file = os.path.join(date_dir, "all.csv")
                if not os.path.exists(csv_file): continue

                table_name = "institutional_summary"
                try:
                    target_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

                    if not force_reimport and date_exists_in_db(engine, table_name, target_date):
                        print(f"Skipping {table_name} - {date_str} (already in DB)")
                        continue

                    print(f"Processing {table_name} - {date_str}...")
                    df = pl.read_csv(csv_file)
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    if force_reimport:
                        delete_by_date(engine, table_name, target_date)

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

        # --- 特別處理 margin_summary (市場信用交易彙總) ---
        if category == "margin_summary":
            # ... (現有邏輯保持不變)
            continue

        # --- 特別處理 quarterly_reports (公司季報) ---
        if category == "quarterly_reports":
            date_dirs = sorted(glob.glob(os.path.join(cat_path, "date=*")))

            for date_dir in date_dirs:
                date_str = date_dir.split("=")[1] # YYYYQX

                # 季報日期過濾邏輯略有不同，若有設定 START_DATE/END_DATE (YYYYMMDD) 則轉換比較
                if start_date or end_date:
                    # 粗略轉換: 2020Q1 -> 2020-03-31 (季末)
                    year = int(date_str[:4])
                    q = int(date_str[5])
                    q_month = q * 3
                    q_date = datetime.datetime(year, q_month, 1)
                    if start_date and q_date < start_date.replace(day=1): continue
                    if end_date and q_date > end_date.replace(day=1): continue

                csv_file = os.path.join(date_dir, "all.csv")
                if not os.path.exists(csv_file): continue

                table_name = "quarterly_reports"
                try:
                    if not force_reimport and date_exists_in_db(engine, table_name, date_str):
                        print(f"Skipping {table_name} - {date_str} (already in DB)")
                        continue

                    print(f"Processing {table_name} - {date_str}...")
                    df = pl.read_csv(csv_file, schema_overrides={"symbol": pl.Utf8})
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    df = filter_etf(df)
                    if df.height == 0:
                        print("  -> No data after filtering ETFs, skipping.")
                        continue

                    if force_reimport:
                        delete_by_date(engine, table_name, date_str)

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
            continue

        # --- 一般處理 (daily_quotes, etc.) ---
        date_dirs = glob.glob(os.path.join(cat_path, "date=*"))

        for date_dir in sorted(date_dirs):
            date_str = date_dir.split("=")[1]

            try:
                current_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                if start_date and current_date < start_date: continue
                if end_date and current_date > end_date: continue
            except ValueError:
                continue

            csv_files = glob.glob(os.path.join(date_dir, "*.csv"))
            for csv_file in csv_files:
                market = os.path.basename(csv_file).split(".")[0]
                table_name = category

                try:
                    target_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

                    if not force_reimport and date_exists_in_db(engine, table_name, target_date, market=market):
                        print(f"Skipping {table_name} - {date_str} - {market} (already in DB)")
                        continue

                    print(f"Processing {table_name} - {date_str} - {market}...")

                    df = pl.read_csv(csv_file)
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    df = filter_etf(df)
                    if df.height == 0:
                        print("  -> No data after filtering ETFs, skipping.")
                        continue

                    # 過濾 OHLCV 全為 0 或 null 的無效資料（停牌或資料缺失）
                    if table_name == "daily_quotes":
                        ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
                        if ohlcv_cols:
                            before = df.height
                            df = df.filter(
                                ~pl.all_horizontal(
                                    (pl.col(c).is_null() | (pl.col(c) == 0)) for c in ohlcv_cols
                                )
                            )
                            filtered = before - df.height
                            if filtered > 0:
                                print(f"  -> Filtered {filtered} rows with all-zero/null OHLCV.")
                            if df.height == 0:
                                print("  -> No data after filtering zero OHLCV, skipping.")
                                continue

                    if force_reimport:
                        delete_by_date(engine, table_name, target_date, market=market)

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
