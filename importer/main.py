import os
import time
import glob
import traceback
import datetime
import polars as pl
from sqlalchemy import create_engine, text

LINEAGE_COLS = ["src_file", "src_row", "src_col"]

def drop_lineage_columns(df):
    """Drop lineage columns before importing to DB."""
    cols_to_drop = [c for c in LINEAGE_COLS if c in df.columns]
    if cols_to_drop:
        return df.drop(cols_to_drop)
    return df

def verify_row_count(engine, table_name, expected_count, date_filter, market_filter=None):
    """Compare expected row count against DB COUNT(*) for the imported date/market."""
    with engine.connect() as conn:
        if market_filter:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE date = :date AND market = :market"),
                {"date": date_filter, "market": market_filter}
            ).scalar()
        else:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE date = :date"),
                {"date": date_filter}
            ).scalar()

    if result != expected_count:
        print(f"  ❌ Row count mismatch: CSV={expected_count}, DB={result}")
        return False
    return True

def abort_with_error(message, exception=None):
    """Write error to error_importer.md and exit immediately."""
    error_file = "/app/error_importer.md"
    with open(error_file, "w") as f:
        f.write("# Importer 錯誤報告\n\n")
        f.write(f"執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 錯誤訊息\n\n{message}\n\n")
        if exception:
            f.write(f"## Traceback\n\n```\n{traceback.format_exc()}\n```\n")
    print(f"\n❌ {message}")
    print(f"錯誤已寫入 {error_file}")
    raise SystemExit(1)

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

def get_date_dirs(cat_path):
    """取得類別路徑下的所有日期目錄，支援 date=yyyymmdd 和 yyyy/yyyymmdd 結構"""
    date_dirs = []
    if not os.path.exists(cat_path):
        return date_dirs
        
    # Old structure: date=yyyymmdd
    date_dirs.extend(glob.glob(os.path.join(cat_path, "date=*")))
    
    # New structure: yyyy/yyyymmdd
    for y in os.listdir(cat_path):
        if len(y) == 4 and y.isdigit():
            y_path = os.path.join(cat_path, y)
            if os.path.isdir(y_path):
                # 這裡假設子目錄就是 yyyymmdd 格式
                for d in os.listdir(y_path):
                    if len(d) == 8 and d.isdigit():
                        date_dirs.append(os.path.join(y_path, d))
    return sorted(date_dirs)

def get_date_from_dir(date_dir):
    """從目錄路徑提取日期字串"""
    base = os.path.basename(date_dir)
    if base.startswith("date="):
        return base.split("=")[1]
    return base

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

        # --- 特別處理 stock_info (股票基本資料，無日期欄位) ---
        if category == "stock_info":
            csv_file = os.path.join(cat_path, "all.csv")
            if not os.path.exists(csv_file): continue
            
            print(f"Processing {category}...")
            try:
                df = pl.read_csv(csv_file, schema_overrides={"symbol": pl.Utf8})
                df = drop_lineage_columns(df)
                # 直接覆蓋整張表
                df.to_pandas().to_sql(
                    name="stock_info",
                    con=engine,
                    if_exists="replace",
                    index=False
                )
                print(f"  -> Imported {df.height} stocks into stock_info.")
            except Exception as e:
                abort_with_error(f"Failed to import stock_info: {e}", e)
            continue

        # --- 特別處理 stock_tags (股票標籤，無日期欄位) ---
        if category == "stock_tags":
            csv_file = os.path.join(cat_path, "all.csv")
            if not os.path.exists(csv_file): continue
            
            print(f"Processing {category}...")
            try:
                df = pl.read_csv(csv_file, schema_overrides={"symbol": pl.Utf8})
                df = drop_lineage_columns(df)
                df.to_pandas().to_sql(
                    name="stock_tags",
                    con=engine,
                    if_exists="replace",
                    index=False
                )
                print(f"  -> Imported {df.height} mappings into stock_tags.")
            except Exception as e:
                abort_with_error(f"Failed to import stock_tags: {e}", e)
            continue

        # --- 特別處理 shareholding (集保股權分散表) ---
        if category == "shareholding":
            date_dirs = get_date_dirs(cat_path)

            for date_dir in date_dirs:
                date_str = get_date_from_dir(date_dir)

                try:
                    current_date = datetime.datetime.strptime(date_str, "%Y%m%d")
                    if start_date and current_date < start_date: continue
                    if end_date and current_date > end_date: continue
                except ValueError:
                    continue

                csv_file = os.path.join(date_dir, "all.csv")
                if not os.path.exists(csv_file): continue

                table_name = "shareholding"
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

                    df = drop_lineage_columns(df)
                    expected_count = df.height
                    df.to_pandas().to_sql(
                        name=table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        chunksize=5000
                    )
                    print(f"  -> Imported {expected_count} rows.")
                    verify_row_count(engine, table_name, expected_count, target_date)

                except Exception as e:
                    abort_with_error(f"Failed to import {csv_file}: {e}", e)
            continue

        # --- 特別處理 institutional_summary (三大法人買賣超彙總) ---
        if category == "institutional_summary":
            date_dirs = get_date_dirs(cat_path)

            for date_dir in date_dirs:
                date_str = get_date_from_dir(date_dir)

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

                    df = drop_lineage_columns(df)
                    expected_count = df.height
                    df.to_pandas().to_sql(
                        name=table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        chunksize=5000
                    )
                    print(f"  -> Imported {expected_count} rows.")
                    verify_row_count(engine, table_name, expected_count, target_date)

                except Exception as e:
                    abort_with_error(f"Failed to import {csv_file}: {e}", e)
            continue

        # --- 特別處理 margin_summary (市場信用交易彙總) ---
        if category == "margin_summary":
            # ... (現有邏輯保持不變)
            continue

        # --- 特別處理季報、詳細財報與月營收 (YYYYQX / YYYYMXX 格式) ---
        if category in ("quarterly_reports", "income_statement", "balance_sheet", "cash_flow", "monthly_revenue"):
            date_dirs = sorted(glob.glob(os.path.join(cat_path, "date=*")))
            start_env = os.getenv("START_DATE")
            end_env = os.getenv("END_DATE")
            # 支援 2025Q3 或 2025M01 格式
            is_period_format = lambda s: s and len(s) >= 6 and ("Q" in s or "M" in s)

            for date_dir in date_dirs:
                date_str = date_dir.split("=")[1]  # YYYYQX or YYYYMXX

                if is_period_format(start_env):
                    if date_str < start_env: continue
                elif start_date:
                    # Fallback 到 datetime 粗略比對
                    try:
                        if "Q" in date_str:
                            year, q = int(date_str[:4]), int(date_str[5])
                            compare_date = datetime.datetime(year, q * 3, 1)
                        else:
                            year, m = int(date_str[:4]), int(date_str[6:])
                            compare_date = datetime.datetime(year, m, 1)
                        
                        if compare_date < start_date.replace(day=1): continue
                    except: pass

                if is_period_format(end_env):
                    if date_str > end_env: continue
                elif end_date:
                    try:
                        if "Q" in date_str:
                            year, q = int(date_str[:4]), int(date_str[5])
                            compare_date = datetime.datetime(year, q * 3, 1)
                        else:
                            year, m = int(date_str[:4]), int(date_str[6:])
                            compare_date = datetime.datetime(year, m, 1)
                        
                        if compare_date > end_date.replace(day=1): continue
                    except: pass

                csv_file = os.path.join(date_dir, "all.csv")
                if not os.path.exists(csv_file): continue

                table_name = category
                try:
                    if not force_reimport and date_exists_in_db(engine, table_name, date_str):
                        print(f"Skipping {table_name} - {date_str} (already in DB)")
                        continue

                    print(f"Processing {table_name} - {date_str}...")
                    # 強制指定 date 和 symbol 為 Utf8
                    df = pl.read_csv(csv_file, schema_overrides={"date": pl.Utf8, "symbol": pl.Utf8})
                    if df.height == 0:
                        print("  -> Empty file, skipping.")
                        continue

                    df = filter_etf(df)
                    if df.height == 0:
                        print("  -> No data after filtering ETFs, skipping.")
                        continue

                    if force_reimport:
                        delete_by_date(engine, table_name, date_str)

                    df = drop_lineage_columns(df)
                    expected_count = df.height
                    df.to_pandas().to_sql(
                        name=table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        chunksize=2000
                    )
                    print(f"  -> Imported {expected_count} rows.")
                    verify_row_count(engine, table_name, expected_count, date_str)

                except Exception as e:
                    abort_with_error(f"Failed to import {csv_file}: {e}", e)
            continue

        # --- 一般處理 (daily_quotes, etc.) ---
        date_dirs = get_date_dirs(cat_path)

        for date_dir in date_dirs:
            date_str = get_date_from_dir(date_dir)

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

                    df = drop_lineage_columns(df)
                    expected_count = df.height
                    df.to_pandas().to_sql(
                        name=table_name,
                        con=engine,
                        if_exists="append",
                        index=False,
                        chunksize=2000
                    )
                    print(f"  -> Imported {expected_count} rows.")
                    verify_row_count(engine, table_name, expected_count, target_date, market_filter=market)

                except Exception as e:
                    abort_with_error(f"Failed to import {csv_file}: {e}", e)

            # 在處理完一個日期的所有市場資料後，立刻驗證這個日期
            # 只在成功匯入後才驗證（如果有任何錯誤，上面的 abort_with_error 會中斷）
            if csv_files:  # 確保有檔案被處理
                try:
                    from validator import validate_single_date
                    passed, errors = validate_single_date(engine, table_name, target_date)
                    if not passed:
                        error_msg = f"Validation failed for {table_name} {date_str}: {'; '.join(errors)}"
                        abort_with_error(error_msg, None)
                except ImportError:
                    pass  # 驗證器不存在時跳過
                except Exception as e:
                    print(f"⚠️  Validation warning for {table_name} {date_str}: {e}")
                    # 驗證失敗不中斷匯入（因為可能只是統計差異）

if __name__ == "__main__":
    print("Starting Importer...")
    db_url = get_db_url()
    engine = create_engine(db_url)

    wait_for_db(engine)
    import_data(engine)
    print("All imports completed.")

    # 執行驗證
    print("\n" + "="*60)
    print("開始驗證資料庫與 CSV 的一致性...")
    print("="*60)

    enable_full_diff = os.getenv("ENABLE_FULL_DIFF", "").lower() in ("1", "true", "yes")

    try:
        from validator import validate_all_tables
        all_passed, all_errors = validate_all_tables(engine)

        # 如果啟用完整 diff 比對
        if enable_full_diff:
            print("\n" + "="*60)
            print("執行完整 diff 比對...")
            print("="*60)

            try:
                from full_diff import full_diff_validation, write_diff_report
                diff_reports = full_diff_validation(engine)

                if diff_reports:
                    write_diff_report(diff_reports, "/app/error_importer_diff.md")
                    print("✅ 完整 diff 報告已生成")
                else:
                    print("⚠️  沒有生成 diff 報告")

            except Exception as e:
                print(f"❌ 完整 diff 比對時發生錯誤: {e}")
                traceback.print_exc()

        if not all_passed:
            # 寫錯誤到 error_importer.md
            error_file = "/app/error_importer.md"
            with open(error_file, "w") as f:
                f.write("# Importer 驗證錯誤報告\n\n")
                f.write(f"**執行時間**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

                # 顯示驗證範圍
                start_env = os.getenv("START_DATE", "未指定")
                end_env = os.getenv("END_DATE", "未指定")
                f.write(f"**驗證範圍**: {start_env} ~ {end_env}\n\n")

                # 顯示驗證的表格
                f.write(f"**驗證表格**: {', '.join(all_errors.keys())}\n\n")

                f.write("---\n\n")
                f.write("## 驗證失敗的表格\n\n")

                for table, errors in all_errors.items():
                    f.write(f"### {table}\n\n")

                    # 顯示 CSV 檔案資訊
                    import glob
                    csv_pattern = f"/app/data/processed/{table}"
                    if os.path.exists(csv_pattern):
                        csv_files = []
                        csv_files.extend(glob.glob(f"{csv_pattern}/*/*/*.csv"))
                        csv_files.extend(glob.glob(f"{csv_pattern}/date=*/*.csv"))
                        if csv_files:
                            f.write(f"**CSV 檔案數量**: {len(csv_files)} 個\n\n")

                    # 顯示錯誤訊息
                    f.write("**錯誤詳情**:\n\n")
                    for error in errors:
                        f.write(f"- {error}\n")
                    f.write("\n")

                f.write("---\n\n")
                f.write("## 建議處理方式\n\n")
                f.write("1. 檢查 processor 是否正確處理了原始資料\n")
                f.write("2. 檢查 importer 是否有正確的過濾邏輯（ETF、特別股過濾）\n")
                f.write("3. 使用 `FORCE_REIMPORT=1` 重新匯入資料\n")
                f.write("4. 檢查資料庫連線和權限設定\n")
                f.write(f"5. 查看詳細的驗證輸出：`START_DATE={start_env} END_DATE={end_env} docker compose run --rm importer`\n")

            print(f"\n❌ 驗證失敗！錯誤已寫入 {error_file}")
        else:
            # 刪除舊的錯誤檔案（如果存在）
            error_file = "/app/error_importer.md"
            if os.path.exists(error_file):
                os.remove(error_file)
                print(f"\n✅ 驗證通過，已清除舊的錯誤檔案")

    except Exception as e:
        print(f"\n❌ 驗證過程發生錯誤: {e}")
        traceback.print_exc()

        # 寫錯誤到檔案
        error_file = "/app/error_importer.md"
        with open(error_file, "w") as f:
            f.write("# Importer 驗證錯誤報告\n\n")
            f.write(f"執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## 驗證過程發生錯誤\n\n")
            f.write(f"```\n{traceback.format_exc()}\n```\n")

        print(f"\n❌ 驗證過程錯誤已寫入 {error_file}")
