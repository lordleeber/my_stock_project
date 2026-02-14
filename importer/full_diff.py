"""
完整 diff 比對：逐行比對資料庫和 CSV 的內容差異
"""
import os
import glob
import polars as pl
from sqlalchemy import text


def export_table_to_df(engine, table_name):
    """從資料庫匯出表格資料到 DataFrame"""
    print(f"  📤 匯出資料庫表格: {table_name}")

    with engine.connect() as conn:
        # 檢查表格是否存在
        exists = conn.execute(text(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"
        ), {"name": table_name}).scalar()

        if not exists:
            print(f"  ⚠️  表格不存在: {table_name}")
            return None

        # 獲取欄位列表
        result = conn.execute(text(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = :name
            ORDER BY ordinal_position
        """), {"name": table_name})

        columns = [(row[0], row[1]) for row in result]

        # 匯出資料（所有欄位轉成 text 避免型別問題）
        col_names = [col[0] for col in columns]
        col_casts = [f'"{col}"::text AS "{col}"' for col in col_names]
        query = f"SELECT {', '.join(col_casts)} FROM {table_name} ORDER BY date, symbol"

        try:
            result = conn.execution_options(stream_results=True).execute(text(query))
            rows = result.fetchall()

            if not rows:
                print(f"  ⚠️  表格為空: {table_name}")
                return None

            # 轉成 polars DataFrame
            df = pl.DataFrame({col: [] for col in col_names})
            data_dict = {col: [row[i] for row in rows] for i, col in enumerate(col_names)}
            df = pl.DataFrame(data_dict)

            print(f"  ✅ 匯出 {len(df)} 筆資料")
            return df

        except Exception as e:
            print(f"  ❌ 匯出失敗: {e}")
            return None


def load_csv_to_df(table_name, data_dir="/app/data/processed"):
    """讀取所有 CSV 並合併成 DataFrame"""
    print(f"  📥 讀取 CSV 檔案: {table_name}")

    # 找出所有 CSV 檔案 (支援 date=yyyymmdd 和 yyyy/yyyymmdd 結構)
    csv_files = []
    # 支援新結構 yyyy/yyyymmdd/*.csv
    csv_files.extend(glob.glob(f"{data_dir}/{table_name}/*/*/sii.csv"))
    csv_files.extend(glob.glob(f"{data_dir}/{table_name}/*/*/otc.csv"))
    csv_files.extend(glob.glob(f"{data_dir}/{table_name}/*/*/all.csv"))
    
    # 支援舊結構 date=yyyymmdd/*.csv
    csv_files.extend(glob.glob(f"{data_dir}/{table_name}/date=*/sii.csv"))
    csv_files.extend(glob.glob(f"{data_dir}/{table_name}/date=*/otc.csv"))
    csv_files.extend(glob.glob(f"{data_dir}/{table_name}/date=*/all.csv"))

    if not csv_files:
        print(f"  ⚠️  找不到 CSV 檔案")
        return None

    print(f"  📁 找到 {len(csv_files)} 個檔案")

    # 讀取並合併（所有欄位當作字串避免型別問題）
    dfs = []
    for csv_file in sorted(csv_files):
        try:
            # 先讀取 schema
            df_sample = pl.read_csv(csv_file, n_rows=1)
            # 所有欄位都當作 Utf8
            schema_overrides = {col: pl.Utf8 for col in df_sample.columns}
            df = pl.read_csv(csv_file, schema_overrides=schema_overrides)
            dfs.append(df)
        except Exception as e:
            print(f"  ⚠️  讀取失敗: {csv_file} - {e}")

    if not dfs:
        print(f"  ⚠️  無法讀取任何 CSV")
        return None

    df_all = pl.concat(dfs)

    # 排序（與資料庫匯出順序一致）
    if 'date' in df_all.columns and 'symbol' in df_all.columns:
        df_all = df_all.sort(['date', 'symbol'])
    elif 'date' in df_all.columns:
        df_all = df_all.sort('date')

    print(f"  ✅ 讀取 {len(df_all)} 筆資料")
    return df_all


def normalize_dataframe(df, name):
    """標準化 DataFrame（處理 null、空字串、型別）"""
    print(f"  🔄 標準化 {name} DataFrame")

    # 將所有欄位轉成字串
    for col in df.columns:
        df = df.with_columns(pl.col(col).cast(pl.Utf8))

    # 將 null 和空字串統一處理
    for col in df.columns:
        df = df.with_columns(
            pl.when(pl.col(col).is_null())
            .then(pl.lit(""))
            .otherwise(pl.col(col))
            .alias(col)
        )

    # 去除數值的前後空白
    for col in df.columns:
        df = df.with_columns(pl.col(col).str.strip_chars().alias(col))

    return df


def compare_dataframes(df_csv, df_db, table_name):
    """比對兩個 DataFrame 並找出差異"""
    print(f"\n{'='*60}")
    print(f"🔍 完整 diff 比對: {table_name}")
    print(f"{'='*60}")

    if df_csv is None or df_db is None:
        print("❌ 無法比對（資料不完整）")
        return None

    print(f"CSV 筆數: {len(df_csv):,}")
    print(f"DB  筆數: {len(df_db):,}")

    # 標準化兩個 DataFrame
    df_csv = normalize_dataframe(df_csv, "CSV")
    df_db = normalize_dataframe(df_db, "DB")

    # 確保欄位順序一致
    if set(df_csv.columns) != set(df_db.columns):
        print(f"\n⚠️  欄位不一致！")
        print(f"只在 CSV: {set(df_csv.columns) - set(df_db.columns)}")
        print(f"只在 DB:  {set(df_db.columns) - set(df_csv.columns)}")

        # 取交集欄位
        common_cols = sorted(set(df_csv.columns) & set(df_db.columns))
        df_csv = df_csv.select(common_cols)
        df_db = df_db.select(common_cols)
        print(f"使用共同欄位: {len(common_cols)} 個")
    else:
        # 統一欄位順序
        df_db = df_db.select(df_csv.columns)

    # 建立唯一鍵（用於比對）
    key_cols = []
    if 'date' in df_csv.columns:
        key_cols.append('date')
    if 'symbol' in df_csv.columns:
        key_cols.append('symbol')
    if 'market' in df_csv.columns and 'symbol' not in df_csv.columns:
        key_cols.append('market')

    if not key_cols:
        print("❌ 無法確定比對鍵（需要 date 或 symbol 欄位）")
        return None

    print(f"比對鍵: {', '.join(key_cols)}")

    # 創建複合鍵
    df_csv = df_csv.with_columns(
        pl.concat_str(key_cols, separator='|').alias('_key')
    )
    df_db = df_db.with_columns(
        pl.concat_str(key_cols, separator='|').alias('_key')
    )

    # 找出差異
    csv_keys = set(df_csv['_key'].to_list())
    db_keys = set(df_db['_key'].to_list())

    only_in_csv = csv_keys - db_keys
    only_in_db = db_keys - csv_keys
    in_both = csv_keys & db_keys

    print(f"\n📊 比對結果:")
    print(f"  只在 CSV: {len(only_in_csv):,} 筆")
    print(f"  只在 DB:  {len(only_in_db):,} 筆")
    print(f"  兩者都有: {len(in_both):,} 筆")

    # 找出數值不同的記錄
    print(f"\n🔎 檢查數值差異...")
    value_diffs = []

    if in_both:
        # 取樣檢查（避免太慢）
        sample_size = min(len(in_both), 10000)
        sample_keys = sorted(in_both)[:sample_size]

        for key in sample_keys:
            row_csv = df_csv.filter(pl.col('_key') == key).drop('_key')
            row_db = df_db.filter(pl.col('_key') == key).drop('_key')

            if len(row_csv) == 0 or len(row_db) == 0:
                continue

            # 比對每個欄位
            diff_cols = []
            for col in row_csv.columns:
                val_csv = row_csv[col][0]
                val_db = row_db[col][0]

                if val_csv != val_db:
                    diff_cols.append((col, val_csv, val_db))

            if diff_cols:
                value_diffs.append((key, diff_cols))

        print(f"  檢查了 {sample_size:,} 筆，發現 {len(value_diffs):,} 筆有數值差異")

    # 產生報告
    report = {
        'table_name': table_name,
        'csv_count': len(df_csv),
        'db_count': len(df_db),
        'only_in_csv': list(only_in_csv)[:100],  # 最多顯示 100 筆
        'only_in_csv_count': len(only_in_csv),
        'only_in_db': list(only_in_db)[:100],
        'only_in_db_count': len(only_in_db),
        'value_diffs': value_diffs[:50],  # 最多顯示 50 筆
        'value_diffs_count': len(value_diffs),
    }

    return report


def full_diff_validation(engine):
    """執行完整 diff 比對"""
    print("\n" + "="*60)
    print("🔬 開始完整 diff 比對...")
    print("="*60)

    # 要驗證的表格
    import_category = os.getenv("IMPORT_CATEGORY")
    if import_category:
        tables = [import_category]
    else:
        tables = [
            'daily_quotes',
            'institutional_investors',
            'margin_trading',
            'pe_ratio',
        ]

    all_reports = {}

    for table in tables:
        print(f"\n{'='*60}")
        print(f"處理表格: {table}")
        print(f"{'='*60}")

        # 檢查是否有對應的 CSV 目錄
        csv_dir = f"/app/data/processed/{table}"
        if not os.path.exists(csv_dir):
            print(f"⏭️  跳過（沒有對應的 CSV 目錄）")
            continue

        try:
            # 匯出 DB 資料
            df_db = export_table_to_df(engine, table)

            # 讀取 CSV 資料
            df_csv = load_csv_to_df(table)

            # 比對
            report = compare_dataframes(df_csv, df_db, table)

            if report:
                all_reports[table] = report

        except Exception as e:
            print(f"❌ 處理時發生錯誤: {e}")
            import traceback
            traceback.print_exc()

    return all_reports


def write_diff_report(reports, output_file="/app/error_importer.log"):
    """寫入 diff 報告"""
    import datetime

    with open(output_file, "w") as f:
        f.write("# Importer 完整 Diff 報告\n\n")
        f.write(f"執行時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        for table_name, report in reports.items():
            f.write(f"## {table_name}\n\n")
            f.write(f"- CSV 筆數: {report['csv_count']:,}\n")
            f.write(f"- DB 筆數: {report['db_count']:,}\n")
            f.write(f"- 差異: {abs(report['csv_count'] - report['db_count']):,}\n\n")

            if report['only_in_csv_count'] > 0:
                f.write(f"### 只在 CSV 存在（{report['only_in_csv_count']:,} 筆）\n\n")
                f.write("前 100 筆:\n```\n")
                for key in report['only_in_csv'][:100]:
                    f.write(f"{key}\n")
                f.write("```\n\n")

            if report['only_in_db_count'] > 0:
                f.write(f"### 只在 DB 存在（{report['only_in_db_count']:,} 筆）\n\n")
                f.write("前 100 筆:\n```\n")
                for key in report['only_in_db'][:100]:
                    f.write(f"{key}\n")
                f.write("```\n\n")

            if report['value_diffs_count'] > 0:
                f.write(f"### 數值差異（{report['value_diffs_count']:,} 筆）\n\n")
                f.write("前 50 筆:\n")
                for key, diffs in report['value_diffs'][:50]:
                    f.write(f"\n**{key}**\n")
                    for col, val_csv, val_db in diffs[:5]:  # 每筆最多顯示 5 個欄位
                        f.write(f"- `{col}`: CSV=`{val_csv}` vs DB=`{val_db}`\n")
                f.write("\n")

            f.write("---\n\n")

        f.write("## 建議處理方式\n\n")
        f.write("1. 檢查「只在 CSV」的資料是否正確匯入\n")
        f.write("2. 檢查「只在 DB」的資料是否為舊資料（應該被刪除）\n")
        f.write("3. 檢查「數值差異」的原因（型別轉換？精度問題？）\n")
        f.write("4. 考慮使用 `FORCE_REIMPORT=1` 重新匯入\n")

    print(f"\n✅ Diff 報告已寫入: {output_file}")
