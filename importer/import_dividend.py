import os
import glob
import polars as pl
from sqlalchemy import create_engine
from import_common import (
    get_db_url, wait_for_db, recalculate_lineage, 
    abort_with_error, get_polars_schema
)

CATEGORY = "dividend"
TABLE_NAME = "dividend"

def run_import():
    engine = create_engine(get_db_url())
    wait_for_db(engine)
    
    processed_base = f"/app/data/processed/{CATEGORY}"
    csv_files = sorted(glob.glob(f"{processed_base}/*/all.csv"))
    
    if not csv_files:
        print(f"No processed files found in {processed_base}")
        return

    all_dfs = []
    schema = get_polars_schema(CATEGORY)
    
    for csv_file in csv_files:
        print(f"Reading {csv_file}...")
        try:
            df = pl.read_csv(csv_file, schema_overrides=schema or {})
            if not df.is_empty():
                df = recalculate_lineage(df, csv_file)
                all_dfs.append(df)
        except Exception as e:
            print(f"  [!] Error reading {csv_file}: {e}")

    if not all_dfs:
        print("No data to import.")
        return

    final_df = pl.concat(all_dfs)
    
    print(f"Importing {final_df.height} rows into {TABLE_NAME}...")
    try:
        # 使用 replace 模式，因為除權息資料通常一次性更新整年度或歷史紀錄
        final_df.to_pandas().to_sql(
            name=TABLE_NAME,
            con=engine,
            if_exists="replace",
            index=False
        )
        print(f"Successfully imported {final_df.height} rows.")
    except Exception as e:
        abort_with_error(f"Failed to import dividend data: {e}", e)

if __name__ == "__main__":
    print("Starting Dividend Importer...")
    run_import()
