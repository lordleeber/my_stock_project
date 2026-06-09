import datetime
import glob
import os

import polars as pl
from sqlalchemy import create_engine, text
from import_common import (
    abort_with_error,
    get_db_url,
    get_polars_schema,
    recalculate_lineage,
    table_exists,
    wait_for_db,
)

CATEGORY = "dividend"
TABLE_NAME = "dividend"
PROCESSED_BASE = f"/app/data/processed/{CATEGORY}"


def _read_year_csv(csv_file, schema):
    df = pl.read_csv(csv_file, schema_overrides=schema or {})
    if df.is_empty():
        return None
    return recalculate_lineage(df, csv_file)


def _full_rebuild(engine, schema):
    """讀取所有年度並 replace 整張表。

    僅用於首次 bootstrap（表尚未存在）或顯式 DIVIDEND_FULL=1（補歷史）。
    """
    csv_files = sorted(glob.glob(f"{PROCESSED_BASE}/*/all.csv"))
    if not csv_files:
        print(f"No processed files found in {PROCESSED_BASE}")
        return

    dfs = []
    for csv_file in csv_files:
        print(f"Reading {csv_file}...")
        df = _read_year_csv(csv_file, schema)
        if df is not None:
            dfs.append(df)

    if not dfs:
        print("No data to import.")
        return

    final_df = pl.concat(dfs)
    print(f"Rebuilding {TABLE_NAME} with {final_df.height} rows (all years)...")
    try:
        final_df.to_pandas().to_sql(
            name=TABLE_NAME, con=engine, if_exists="replace", index=False
        )
        print(f"Successfully rebuilt {TABLE_NAME} ({final_df.height} rows).")
    except Exception as e:
        abort_with_error(f"Failed to rebuild dividend table: {e}", e)


def _import_year(engine, year, schema):
    """單一年度 delete-before-insert，其他年度（immutable）原封不動。

    DELETE + INSERT + 列數驗證全包在「同一筆交易」內：任何一步失敗（含列數
    不符觸發的 abort）都會整筆 rollback，不會留下「當年度已刪除卻沒補回」的
    空窗。pandas to_sql 傳入這條已開啟交易的 connection 時，會沿用同一筆交易
    （不另起、不提前 commit），commit 統一在 with 區塊正常結束時發生。
    """
    csv_file = f"{PROCESSED_BASE}/{year}/all.csv"
    if not os.path.exists(csv_file):
        print(f"No processed file for {year} ({csv_file}); nothing to import.")
        return

    df = _read_year_csv(csv_file, schema)
    if df is None:
        print(f"  -> {year} processed file is empty, skipping.")
        return

    expected = df.height
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"DELETE FROM {TABLE_NAME} WHERE date LIKE :pat"),
                {"pat": f"{year}-%"},
            )
            df.to_pandas().to_sql(
                name=TABLE_NAME, con=conn, if_exists="append", index=False
            )
            got = conn.execute(
                text(f"SELECT count(*) FROM {TABLE_NAME} WHERE date LIKE :pat"),
                {"pat": f"{year}-%"},
            ).scalar()
            if got != expected:
                # 在交易內 abort → SystemExit 觸發 with 區塊 rollback，DELETE 一併回滾。
                abort_with_error(
                    f"Row count mismatch for {TABLE_NAME} {year}: imported={expected}, DB={got}"
                )
        print(f"  -> Imported {expected} rows for {year} (DB {year} now has {got}).")
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Failed to import dividend for {year}: {e}", e)


def run_import():
    engine = create_engine(get_db_url())
    wait_for_db(engine)
    schema = get_polars_schema(CATEGORY)

    full = os.getenv("DIVIDEND_FULL", "0") == "1"
    if full or not table_exists(engine, TABLE_NAME):
        # 表還沒建好或顯式要求 → 全量 rebuild；否則只增量更新當年度。
        _full_rebuild(engine, schema)
        return

    year = str(datetime.date.today().year)
    _import_year(engine, year, schema)


if __name__ == "__main__":
    print("Starting Dividend Importer...")
    run_import()
