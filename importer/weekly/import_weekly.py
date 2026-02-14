import polars as pl

from import_common import (
    abort_with_error,
    date_exists_in_db,
    delete_by_date,
    filter_etf,
    in_daily_range,
    iter_shareholding_files,
    recalculate_lineage,
    run_lineage_validation,
    to_iso_date,
    verify_row_count,
)

WEEKLY_CATEGORIES = {"shareholding"}


def run(engine, config, import_category=None):
    if import_category and import_category not in WEEKLY_CATEGORIES:
        return False
    return import_shareholding_category(engine, config)


def import_shareholding_category(engine, config):
    category = "shareholding"
    table_name = "shareholding"
    cat_path = f"/app/data/processed/{category}"
    imported_any = False

    for date_token, csv_file in iter_shareholding_files(cat_path):
        if not in_daily_range(date_token, config):
            continue

        target_date = to_iso_date(date_token)

        try:
            if not config["force_reimport"] and date_exists_in_db(engine, table_name, target_date):
                print(f"Skipping {table_name} - {date_token} (already in DB)")
                continue

            print(f"Processing {table_name} - {date_token}...")
            df = pl.read_csv(csv_file, schema_overrides={"symbol": pl.Utf8})
            if df.height == 0:
                print("  -> Empty file, skipping.")
                continue
            if "symbol" in df.columns:
                df = df.with_columns(pl.col("symbol").cast(pl.Utf8).str.strip_chars().alias("symbol"))

            df = recalculate_lineage(df, csv_file)
            df = filter_etf(df)
            if df.height == 0:
                print("  -> No data after filtering ETFs, skipping.")
                continue

            if config["force_reimport"]:
                delete_by_date(engine, table_name, target_date)

            expected_count = df.height
            df.to_pandas().to_sql(
                name=table_name,
                con=engine,
                if_exists="append",
                index=False,
                chunksize=5000,
            )
            print(f"  -> Imported {expected_count} rows.")
            verify_row_count(engine, table_name, expected_count, target_date)
            run_lineage_validation(engine, table_name, target_date)
            imported_any = True
        except Exception as e:
            abort_with_error(f"Failed to import {csv_file}: {e}", e)

    return imported_any
