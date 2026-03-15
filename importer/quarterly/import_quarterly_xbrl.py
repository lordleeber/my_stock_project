import os

import polars as pl

from import_common import (
    abort_with_error,
    date_exists_in_db,
    delete_by_date,
    filter_etf,
    get_polars_schema,
    in_period_range,
    iter_period_dirs,
    run_lineage_validation,
    verify_row_count,
)


CATEGORY = "quarterly_reports_xbrl"
TABLE_NAME = "quarterly_reports_xbrl"
FILE_PERIOD_TYPES = (
    ("all_quarter.csv", "quarter"),
    ("all_accumulated.csv", "accumulated"),
)


def run(engine, config, import_category=None):
    if import_category and import_category != CATEGORY:
        return False

    cat_path = f"/app/data/processed/{CATEGORY}"
    imported_any = False
    base_schema = get_polars_schema(CATEGORY) or {}
    base_schema.update({"date": pl.Utf8, "symbol": pl.Utf8})

    for period_token, period_dir in iter_period_dirs(cat_path):
        if not in_period_range(period_token, config):
            continue

        sources: list[tuple[str, str]] = []
        for filename, period_type in FILE_PERIOD_TYPES:
            csv_file = os.path.join(period_dir, filename)
            if os.path.exists(csv_file):
                sources.append((csv_file, period_type))
        if not sources:
            continue

        try:
            if not config["force_reimport"] and date_exists_in_db(
                engine, TABLE_NAME, period_token
            ):
                print(f"Skipping {TABLE_NAME} - {period_token} (already in DB)")
                continue

            print(f"Processing {TABLE_NAME} - {period_token}...")
            dfs: list[pl.DataFrame] = []
            for csv_file, period_type in sources:
                df_part = pl.read_csv(csv_file, schema_overrides=base_schema)
                if df_part.height == 0:
                    print(f"  -> Empty file, skipping {csv_file}.")
                    continue

                # Keep quarter vs accumulated source explicit in one table.
                df_part = df_part.with_columns(
                    pl.lit(period_type).cast(pl.Utf8).alias("period_type")
                )
                dfs.append(df_part)

            if not dfs:
                continue

            df = pl.concat(dfs, how="vertical_relaxed")
            df = filter_etf(df)
            if df.height == 0:
                print("  -> No data after filtering ETFs, skipping.")
                continue

            if config["force_reimport"]:
                delete_by_date(engine, TABLE_NAME, period_token)

            expected_count = df.height
            df.to_pandas().to_sql(
                name=TABLE_NAME,
                con=engine,
                if_exists="append",
                index=False,
                chunksize=2000,
            )
            print(f"  -> Imported {expected_count} rows.")
            verify_row_count(engine, TABLE_NAME, expected_count, period_token)
            run_lineage_validation(engine, TABLE_NAME, period_token)
            imported_any = True
        except Exception as e:
            abort_with_error(
                f"Failed to import {TABLE_NAME} for {period_token}: {e}", e
            )

    return imported_any
