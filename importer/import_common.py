import datetime
import glob
import os
import re
import time
import traceback
from pathlib import Path

import polars as pl
from sqlalchemy import text
import sys

# 加入 common 目錄到搜尋路徑
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.schemas import get_polars_schema


CODE_COL_RE = re.compile(r"^code(\d+)$")
VALUE_COL_RE = re.compile(r"^value(\d+)$")


def abort_with_error(message, exception=None):
    """Write error to error_importer.log and exit immediately."""
    error_file = "/app/error_importer.log"
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
        except Exception:
            print(f"Waiting for database... ({retries} retries left)")
            time.sleep(2)
            retries -= 1
    raise Exception("Database connection failed")


def parse_date_env(date_str):
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.datetime.strptime(date_str, "%Y%m%d")
    except ValueError:
        return None


def is_period_token(token):
    return bool(token and re.match(r"^\d{4}(Q[1-4]|M\d{2})$", token))


def get_filter_dates():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    start_date = parse_date_env(start_env)
    end_date = parse_date_env(end_env)
    return start_date, end_date, start_env, end_env


def get_run_config():
    start_date, end_date, start_env, end_env = get_filter_dates()
    force_reimport = os.getenv("FORCE_REIMPORT", "").lower() in ("1", "true", "yes")
    return {
        "start_date": start_date,
        "end_date": end_date,
        "start_env": start_env,
        "end_env": end_env,
        "force_reimport": force_reimport,
    }


def print_run_config(config):
    if config["start_date"]:
        print(f"Filter Start Date: {config['start_date'].strftime('%Y-%m-%d')}")
    if config["end_date"]:
        print(f"Filter End Date: {config['end_date'].strftime('%Y-%m-%d')}")
    if config["force_reimport"]:
        print("FORCE_REIMPORT: enabled (will delete and re-import existing data)")


def table_exists(engine, table_name):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"),
            {"name": table_name},
        ).scalar()


def date_exists_in_db(engine, table_name, target_date, market=None):
    if not table_exists(engine, table_name):
        return False

    with engine.connect() as conn:
        if market is not None:
            result = conn.execute(
                text(f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE date = :date AND market = :market)"),
                {"date": target_date, "market": market},
            ).scalar()
        else:
            result = conn.execute(
                text(f"SELECT EXISTS (SELECT 1 FROM {table_name} WHERE date = :date)"),
                {"date": target_date},
            ).scalar()
    return result


def delete_by_date(engine, table_name, target_date, market=None):
    with engine.begin() as conn:
        if market is not None:
            conn.execute(
                text(f"DELETE FROM {table_name} WHERE date = :date AND market = :market"),
                {"date": target_date, "market": market},
            )
        else:
            conn.execute(
                text(f"DELETE FROM {table_name} WHERE date = :date"),
                {"date": target_date},
            )


def verify_row_count(engine, table_name, expected_count, date_filter, market_filter=None):
    with engine.connect() as conn:
        if market_filter is not None:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE date = :date AND market = :market"),
                {"date": date_filter, "market": market_filter},
            ).scalar()
        else:
            result = conn.execute(
                text(f"SELECT COUNT(*) FROM {table_name} WHERE date = :date"),
                {"date": date_filter},
            ).scalar()

    if result != expected_count:
        scope = f"{table_name} date={date_filter}"
        if market_filter is not None:
            scope += f" market={market_filter}"
        raise RuntimeError(f"Row count mismatch for {scope}: CSV={expected_count}, DB={result}")
    return True


def recalculate_lineage(df, csv_file_path):
    lineage_cols_to_drop = [c for c in ["src_file", "src_row", "src_col"] if c in df.columns]
    if lineage_cols_to_drop:
        df = df.drop(lineage_cols_to_drop)

    num_data_cols = len([c for c in df.columns if c not in ["pced_file", "pced_row", "pced_col"]])
    pced_col_str = "#".join(str(i + 1) for i in range(num_data_cols))

    return df.with_columns(
        [
            pl.lit(csv_file_path).alias("pced_file"),
            (pl.arange(0, df.height) + 2).alias("pced_row"),
            pl.lit(pced_col_str).alias("pced_col"),
        ]
    )


def filter_etf(df):
    if "symbol" not in df.columns:
        return df

    symbol_col = pl.col("symbol").cast(pl.Utf8)
    original_count = df.height
    # 只保留剛好 4 碼且全部為數字的代號
    df = df.filter(symbol_col.str.contains(r"^\d{4}$"))

    filtered_count = original_count - df.height
    if filtered_count > 0:
        print(f"  -> Filtered out {filtered_count} non-stock records (kept only 4-digit numeric symbols)")
    return df


def apply_daily_quotes_filter(df, table_name):
    if table_name != "daily_quotes":
        return df

    ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    if not ohlcv_cols:
        return df

    before = df.height
    df = df.filter(~pl.all_horizontal((pl.col(c).is_null() | (pl.col(c) == 0)) for c in ohlcv_cols))
    filtered = before - df.height
    if filtered > 0:
        print(f"  -> Filtered {filtered} rows with all-zero/null OHLCV.")
    return df


def iter_daily_date_dirs(cat_path):
    if not os.path.exists(cat_path):
        return []

    date_dirs = []
    for y_path in sorted(Path(cat_path).glob("[0-9][0-9][0-9][0-9]")):
        if not y_path.is_dir():
            continue
        for d_path in sorted(y_path.glob("[0-9]" * 8)):
            if d_path.is_dir():
                date_dirs.append((d_path.name, str(d_path)))

    # Legacy path support: date=YYYYMMDD
    for legacy_path in sorted(Path(cat_path).glob("date=*")):
        if legacy_path.is_dir():
            date_dirs.append((legacy_path.name.split("=", 1)[1], str(legacy_path)))

    return sorted(date_dirs)


def iter_period_dirs(cat_path):
    if not os.path.exists(cat_path):
        return []

    period_dirs = []
    for y_path in sorted(Path(cat_path).glob("[0-9][0-9][0-9][0-9]")):
        if not y_path.is_dir():
            continue
        for p_path in sorted(y_path.iterdir()):
            if p_path.is_dir() and is_period_token(p_path.name):
                period_dirs.append((p_path.name, str(p_path)))

    # Legacy path support: date=YYYYQX / date=YYYYMXX
    for legacy_path in sorted(Path(cat_path).glob("date=*")):
        if legacy_path.is_dir():
            token = legacy_path.name.split("=", 1)[1]
            if is_period_token(token):
                period_dirs.append((token, str(legacy_path)))

    return sorted(period_dirs)


def iter_shareholding_files(cat_path):
    if not os.path.exists(cat_path):
        return []

    files = []

    # New path: /processed/shareholding/YYYY/YYYYMMDD.csv
    for y_path in sorted(Path(cat_path).glob("[0-9][0-9][0-9][0-9]")):
        if not y_path.is_dir():
            continue
        for csv_path in sorted(y_path.glob("[0-9]" * 8 + ".csv")):
            date_token = csv_path.stem
            if re.match(r"^\d{8}$", date_token):
                files.append((date_token, str(csv_path)))

    # Legacy path: /processed/shareholding/date=YYYYMMDD/all.csv
    for legacy_path in sorted(Path(cat_path).glob("date=*")):
        if not legacy_path.is_dir():
            continue
        date_token = legacy_path.name.split("=", 1)[1]
        if re.match(r"^\d{8}$", date_token):
            csv_file = legacy_path / "all.csv"
            if csv_file.exists():
                files.append((date_token, str(csv_file)))

    return sorted(files)


def to_iso_date(yyyymmdd):
    return f"{yyyymmdd[:4]}-{yyyymmdd[4:6]}-{yyyymmdd[6:]}"


def in_daily_range(date_token, config):
    try:
        current_date = datetime.datetime.strptime(date_token, "%Y%m%d")
    except ValueError:
        return False

    start_date = config["start_date"]
    end_date = config["end_date"]
    if start_date and current_date < start_date:
        return False
    if end_date and current_date > end_date:
        return False
    return True


def _period_to_compare_date(period_token):
    if "Q" in period_token:
        year = int(period_token[:4])
        q = int(period_token[-1])
        return datetime.datetime(year, q * 3, 1)

    year = int(period_token[:4])
    month = int(period_token[-2:])
    return datetime.datetime(year, month, 1)


def in_period_range(period_token, config):
    start_env = config["start_env"]
    end_env = config["end_env"]
    start_date = config["start_date"]
    end_date = config["end_date"]

    if is_period_token(start_env) and period_token < start_env:
        return False
    if is_period_token(end_env) and period_token > end_env:
        return False

    compare_date = _period_to_compare_date(period_token)
    if start_date and not is_period_token(start_env):
        if compare_date < start_date.replace(day=1):
            return False
    if end_date and not is_period_token(end_env):
        if compare_date > end_date.replace(day=1):
            return False

    return True


def run_lineage_validation(engine, table_name, target_date):
    try:
        from validator import validate_single_date

        passed, errors = validate_single_date(engine, table_name, target_date)
        if not passed:
            abort_with_error(f"Validation failed for {table_name} {target_date}: {'; '.join(errors)}")
    except ImportError:
        return
    except SystemExit:
        raise
    except Exception as e:
        abort_with_error(f"Validation failed for {table_name} {target_date}: {e}", e)


def import_static_all_csv(engine, category, table_name, schema_overrides=None):
    csv_file = f"/app/data/processed/{category}/all.csv"
    if not os.path.exists(csv_file):
        return False

    print(f"Processing {table_name}...")
    try:
        full_schema = get_polars_schema(category) or {}
        if schema_overrides:
            full_schema.update(schema_overrides)
        df = pl.read_csv(csv_file, schema_overrides=full_schema)
        if df.height == 0:
            print("  -> Empty file, skipping.")
            return False

        df = recalculate_lineage(df, csv_file)
        df.to_pandas().to_sql(name=table_name, con=engine, if_exists="replace", index=False)
        print(f"  -> Imported {df.height} rows into {table_name}.")
        return True
    except Exception as e:
        abort_with_error(f"Failed to import {csv_file}: {e}", e)


def import_daily_market_category(
    engine,
    category,
    table_name,
    config,
    schema_overrides=None,
    chunksize=2000,
    apply_etf_filter=True,
):
    cat_path = f"/app/data/processed/{category}"
    imported_any = False

    for date_token, date_dir in iter_daily_date_dirs(cat_path):
        if not in_daily_range(date_token, config):
            continue

        target_date = to_iso_date(date_token)
        csv_files = sorted(glob.glob(os.path.join(date_dir, "*.csv")))
        imported_this_date = False

        for csv_file in csv_files:
            market = os.path.basename(csv_file).split(".")[0]

            try:
                if not config["force_reimport"] and date_exists_in_db(engine, table_name, target_date, market=market):
                    print(f"Skipping {table_name} - {date_token} - {market} (already in DB)")
                    continue

                print(f"Processing {table_name} - {date_token} - {market}...")
                
                # 使用明確定義的 Schema，並與傳入的 override 合併
                full_schema = get_polars_schema(category) or {}
                if schema_overrides:
                    full_schema.update(schema_overrides)
                df = pl.read_csv(csv_file, schema_overrides=full_schema)
                
                if df.height == 0:
                    print("  -> Empty file, skipping.")
                    continue

                df = recalculate_lineage(df, csv_file)
                if apply_etf_filter:
                    df = filter_etf(df)
                    if df.height == 0:
                        print("  -> No data after filtering ETFs, skipping.")
                        continue

                df = apply_daily_quotes_filter(df, table_name)
                if df.height == 0:
                    print("  -> No data after filtering zero OHLCV, skipping.")
                    continue

                if config["force_reimport"]:
                    delete_by_date(engine, table_name, target_date, market=market)

                expected_count = df.height
                df.to_pandas().to_sql(
                    name=table_name,
                    con=engine,
                    if_exists="append",
                    index=False,
                    chunksize=chunksize,
                )
                print(f"  -> Imported {expected_count} rows.")
                verify_row_count(engine, table_name, expected_count, target_date, market_filter=market)
                imported_any = True
                imported_this_date = True
            except Exception as e:
                abort_with_error(f"Failed to import {csv_file}: {e}", e)

        if imported_this_date:
            run_lineage_validation(engine, table_name, target_date)

    return imported_any


def import_daily_all_category(
    engine,
    category,
    table_name,
    config,
    schema_overrides=None,
    chunksize=5000,
    apply_etf_filter=False,
):
    cat_path = f"/app/data/processed/{category}"
    imported_any = False

    for date_token, date_dir in iter_daily_date_dirs(cat_path):
        if not in_daily_range(date_token, config):
            continue

        csv_file = os.path.join(date_dir, "all.csv")
        if not os.path.exists(csv_file):
            continue

        target_date = to_iso_date(date_token)

        try:
            if not config["force_reimport"] and date_exists_in_db(engine, table_name, target_date):
                print(f"Skipping {table_name} - {date_token} (already in DB)")
                continue

            print(f"Processing {table_name} - {date_token}...")
            
            # 使用明確定義的 Schema
            full_schema = get_polars_schema(category) or {}
            if schema_overrides:
                full_schema.update(schema_overrides)
            df = pl.read_csv(csv_file, schema_overrides=full_schema)
            
            if df.height == 0:
                print("  -> Empty file, skipping.")
                continue

            df = recalculate_lineage(df, csv_file)
            if apply_etf_filter:
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
                chunksize=chunksize,
            )
            print(f"  -> Imported {expected_count} rows.")
            verify_row_count(engine, table_name, expected_count, target_date)
            run_lineage_validation(engine, table_name, target_date)
            imported_any = True
        except Exception as e:
            abort_with_error(f"Failed to import {csv_file}: {e}", e)

    return imported_any


def import_period_category(
    engine,
    category,
    table_name,
    config,
    schema_overrides=None,
    chunksize=2000,
    apply_etf_filter=True,
):
    cat_path = f"/app/data/processed/{category}"
    imported_any = False

    for period_token, period_dir in iter_period_dirs(cat_path):
        if not in_period_range(period_token, config):
            continue

        csv_file = os.path.join(period_dir, "all.csv")
        if not os.path.exists(csv_file):
            continue

        try:
            if not config["force_reimport"] and date_exists_in_db(engine, table_name, period_token):
                print(f"Skipping {table_name} - {period_token} (already in DB)")
                continue

            print(f"Processing {table_name} - {period_token}...")
            default_schema = {"date": pl.Utf8, "symbol": pl.Utf8}
            if schema_overrides:
                default_schema.update(schema_overrides)
            df = pl.read_csv(csv_file, schema_overrides=default_schema)
            if df.height == 0:
                print("  -> Empty file, skipping.")
                continue

            df = recalculate_lineage(df, csv_file)
            if apply_etf_filter:
                df = filter_etf(df)
                if df.height == 0:
                    print("  -> No data after filtering ETFs, skipping.")
                    continue

            if config["force_reimport"]:
                delete_by_date(engine, table_name, period_token)

            expected_count = df.height
            df.to_pandas().to_sql(
                name=table_name,
                con=engine,
                if_exists="append",
                index=False,
                chunksize=chunksize,
            )
            print(f"  -> Imported {expected_count} rows.")
            verify_row_count(engine, table_name, expected_count, period_token)
            run_lineage_validation(engine, table_name, period_token)
            imported_any = True
        except Exception as e:
            abort_with_error(f"Failed to import {csv_file}: {e}", e)

    return imported_any


def _xbrl_pair_columns(columns):
    code_cols = {}
    value_cols = {}
    for col in columns:
        m_code = CODE_COL_RE.match(col)
        if m_code:
            code_cols[int(m_code.group(1))] = col
            continue
        m_value = VALUE_COL_RE.match(col)
        if m_value:
            value_cols[int(m_value.group(1))] = col

    indices = sorted(set(code_cols.keys()) & set(value_cols.keys()))
    return [(code_cols[i], value_cols[i]) for i in indices]


def _empty_xbrl_long_df():
    return pl.DataFrame(
        schema={
            "date": pl.Utf8,
            "symbol": pl.Utf8,
            "period": pl.Utf8,
            "period_type": pl.Utf8,
            "account_code": pl.Utf8,
            "value_text": pl.Utf8,
            "value_num": pl.Float64,
        }
    )


def _expand_xbrl_wide_csv(csv_file, period_type):
    df_wide = pl.read_csv(
        csv_file,
        infer_schema_length=0,
        schema_overrides={"date": pl.Utf8, "symbol": pl.Utf8, "period": pl.Utf8},
    )
    if df_wide.height == 0:
        return _empty_xbrl_long_df()

    required_cols = {"date", "symbol"}
    missing_cols = sorted(required_cols - set(df_wide.columns))
    if missing_cols:
        raise RuntimeError(f"Missing required columns in {csv_file}: {', '.join(missing_cols)}")

    if "period" not in df_wide.columns:
        df_wide = df_wide.with_columns(pl.lit(None).cast(pl.Utf8).alias("period"))

    pairs = _xbrl_pair_columns(df_wide.columns)
    if not pairs:
        return _empty_xbrl_long_df()

    parts = []
    for code_col, value_col in pairs:
        part = (
            df_wide.select(
                [
                    pl.col("date").cast(pl.Utf8).alias("date"),
                    pl.col("symbol").cast(pl.Utf8).alias("symbol"),
                    pl.col("period").cast(pl.Utf8).alias("period"),
                    pl.lit(period_type).cast(pl.Utf8).alias("period_type"),
                    pl.col(code_col).cast(pl.Utf8).str.strip_chars().alias("account_code"),
                    pl.col(value_col).cast(pl.Utf8).str.strip_chars().alias("value_text"),
                ]
            )
            .filter(
                pl.col("account_code").is_not_null()
                & (pl.col("account_code") != "")
                & pl.col("value_text").is_not_null()
                & (pl.col("value_text") != "")
            )
            .with_columns(pl.col("value_text").cast(pl.Float64, strict=False).alias("value_num"))
        )
        parts.append(part)

    if not parts:
        return _empty_xbrl_long_df()
    return pl.concat(parts, how="vertical")


def import_xbrl_period_category(
    engine,
    category,
    table_name,
    config,
    file_period_types,
    chunksize=5000,
    apply_etf_filter=True,
):
    cat_path = f"/app/data/processed/{category}"
    imported_any = False

    for period_token, period_dir in iter_period_dirs(cat_path):
        if not in_period_range(period_token, config):
            continue

        sources = []
        for filename, period_type in file_period_types:
            csv_file = os.path.join(period_dir, filename)
            if os.path.exists(csv_file):
                sources.append((csv_file, period_type))

        if not sources:
            continue

        try:
            if not config["force_reimport"] and date_exists_in_db(engine, table_name, period_token):
                print(f"Skipping {table_name} - {period_token} (already in DB)")
                continue

            print(f"Processing {table_name} - {period_token}...")
            dfs = []
            for csv_file, period_type in sources:
                df_part = _expand_xbrl_wide_csv(csv_file, period_type)
                if df_part.height == 0:
                    print(f"  -> Empty or no code/value pairs in {csv_file}, skipping.")
                    continue
                dfs.append(df_part)

            if not dfs:
                continue

            df = pl.concat(dfs, how="vertical")
            if apply_etf_filter:
                df = filter_etf(df)
                if df.height == 0:
                    print("  -> No data after filtering ETFs, skipping.")
                    continue

            if config["force_reimport"]:
                delete_by_date(engine, table_name, period_token)

            expected_count = df.height
            df.to_pandas().to_sql(
                name=table_name,
                con=engine,
                if_exists="append",
                index=False,
                chunksize=chunksize,
            )
            print(f"  -> Imported {expected_count} rows.")
            verify_row_count(engine, table_name, expected_count, period_token)
            run_lineage_validation(engine, table_name, period_token)
            imported_any = True
        except Exception as e:
            abort_with_error(f"Failed to import xbrl {table_name} for {period_token}: {e}", e)

    return imported_any
