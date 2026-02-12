"""
統計值驗證模組：比對資料庫和 CSV 的統計值
"""
import os
import glob
import polars as pl
from sqlalchemy import text


def get_csv_stats(table_name, data_dir="/app/data/processed"):
    """從 CSV 檔案計算統計值"""
    print(f"\n{'='*60}")
    print(f"分析 CSV: {table_name}")
    print(f"{'='*60}")

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
        print(f"⚠️  找不到 CSV 檔案")
        return None

    # 顯示 CSV 檔案的日期範圍
    csv_files_sorted = sorted(csv_files)
    first_file = csv_files_sorted[0]
    last_file = csv_files_sorted[-1]
    print(f"找到 {len(csv_files)} 個 CSV 檔案")
    print(f"日期範圍: {first_file.split('/')[-2]} ~ {last_file.split('/')[-2]}")

    # 讀取所有 CSV 並合併
    dfs = []
    for csv_file in sorted(csv_files):
        try:
            # 使用 infer_schema_length=0 讓 Polars 掃描所有行來推斷型態
            # 這樣可以避免不同檔案間型態不一致的問題
            df = pl.read_csv(csv_file, infer_schema_length=0)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️  讀取失敗: {csv_file} - {e}")

    if not dfs:
        return None

    # 使用 diagonal 模式來處理不同 schema 的 DataFrame
    # 這樣即使欄位型態不完全一致也能合併
    try:
        df_all = pl.concat(dfs, how="diagonal")
    except Exception as e:
        print(f"⚠️  合併 CSV 時發生錯誤: {e}")
        print(f"   嘗試使用寬鬆模式合併...")
        # 如果 diagonal 也失敗，嘗試將所有欄位轉成字串再合併
        dfs_str = []
        for df in dfs:
            df_str = df.with_columns([pl.col(c).cast(pl.Utf8) for c in df.columns])
            dfs_str.append(df_str)
        df_all = pl.concat(dfs_str, how="diagonal")

    # Drop lineage columns (added by processor for QC, not imported to DB)
    lineage_cols = [c for c in ["src_file", "src_row", "src_col"] if c in df_all.columns]
    if lineage_cols:
        df_all = df_all.drop(lineage_cols)

    # 過濾 ETF 和特別股（與 importer 的過濾邏輯一致）
    # 這樣 CSV 統計值才能與資料庫統計值正確比對
    if 'symbol' in df_all.columns:
        original_count = df_all.height
        # 過濾 ETF（代號開頭是 00）和特別股（代號包含英文字母）
        df_all = df_all.filter(
            ~pl.col('symbol').str.starts_with('00') &
            ~pl.col('symbol').str.contains(r'[A-Za-z]')
        )
        filtered_count = original_count - df_all.height
        if filtered_count > 0:
            print(f"已過濾 {filtered_count} 筆 ETF/特別股記錄（與資料庫過濾邏輯一致）")

    # 計算基本統計值
    stats = {
        'total_rows': df_all.height,
        'unique_dates': df_all['date'].n_unique(),
    }

    if 'symbol' in df_all.columns:
        stats['unique_symbols'] = df_all['symbol'].n_unique()

    # 計算日期範圍
    stats['date_range'] = (
        df_all['date'].min(),
        df_all['date'].max()
    )

    # 針對不同表格計算特定統計值
    if table_name == 'daily_quotes':
        # 先將數值欄位轉換為正確的型態，這樣 OHLCV 過濾才能正確比較數值
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df_all.columns:
                try:
                    df_all = df_all.with_columns(pl.col(col).cast(pl.Float64, strict=False))
                except:
                    pass

        # 過濾掉 OHLCV 全為 0 或 NULL 的記錄（與 importer 邏輯完全一致）
        original_count = df_all.height
        ohlcv_cols = [c for c in ['open', 'high', 'low', 'close', 'volume'] if c in df_all.columns]
        if ohlcv_cols:
            # 使用與 importer 相同的邏輯：~pl.all_horizontal(...)
            df_all = df_all.filter(
                ~pl.all_horizontal(
                    (pl.col(c).is_null() | (pl.col(c) == 0)) for c in ohlcv_cols
                )
            )
            filtered_ohlcv = original_count - df_all.height
            if filtered_ohlcv > 0:
                print(f"已過濾 {filtered_ohlcv} 筆 OHLCV 全為 0/NULL 的記錄（與資料庫過濾邏輯一致）")

        # 確保 value 欄位也是數值型態
        if 'value' in df_all.columns:
            try:
                df_all = df_all.with_columns(pl.col('value').cast(pl.Float64, strict=False))
            except:
                pass

        # 更新過濾後的統計值
        stats.update({
            'total_rows': df_all.height,  # 更新為過濾後的行數
            'sum_volume': float(df_all['volume'].sum()),
            'sum_value': float(df_all['value'].sum()),
            'avg_close': float(df_all['close'].mean()),
            'min_close': float(df_all['close'].min()),
            'max_close': float(df_all['close'].max()),
        })
    elif table_name == 'institutional_investors':
        # 確保數值欄位是正確的型態
        numeric_cols = ['foreign_buy', 'trust_buy', 'dealer_net']
        for col in numeric_cols:
            if col in df_all.columns:
                try:
                    df_all = df_all.with_columns(pl.col(col).cast(pl.Float64, strict=False))
                except:
                    pass

        if 'foreign_buy' in df_all.columns:
            stats['sum_foreign_buy'] = float(df_all['foreign_buy'].sum())
        if 'trust_buy' in df_all.columns:
            stats['sum_trust_buy'] = float(df_all['trust_buy'].sum())
        if 'dealer_net' in df_all.columns:
            stats['sum_dealer_net'] = float(df_all['dealer_net'].sum())
    elif table_name == 'margin_trading':
        if 'margin_long_balance' in df_all.columns:
            # 先轉成數值型別（可能是 text），使用 strict=False 忽略無效值
            try:
                df_all = df_all.with_columns(
                    pl.col('margin_long_balance').cast(pl.Float64, strict=False).alias('margin_long_balance')
                )
                stats['sum_margin_long_balance'] = float(df_all['margin_long_balance'].sum())
            except Exception as e:
                print(f"⚠️  計算 margin_long_balance 時發生錯誤: {e}")
                stats['sum_margin_long_balance'] = 0
        if 'margin_short_balance' in df_all.columns:
            try:
                df_all = df_all.with_columns(
                    pl.col('margin_short_balance').cast(pl.Float64, strict=False).alias('margin_short_balance')
                )
                stats['sum_margin_short_balance'] = float(df_all['margin_short_balance'].sum())
            except Exception as e:
                print(f"⚠️  計算 margin_short_balance 時發生錯誤: {e}")
                stats['sum_margin_short_balance'] = 0
    elif table_name == 'pe_ratio':
        if 'pe_ratio' in df_all.columns:
            # 確保 pe_ratio 是數值型態
            try:
                df_all = df_all.with_columns(pl.col('pe_ratio').cast(pl.Float64, strict=False))
            except:
                pass

            # 過濾掉 0 和 null 的 PE ratio
            valid_pe = df_all.filter((pl.col('pe_ratio') > 0) & (pl.col('pe_ratio').is_not_null()))
            if valid_pe.height > 0:
                stats['avg_pe_ratio'] = float(valid_pe['pe_ratio'].mean())

    return stats


def get_db_stats(engine, table_name):
    """從資料庫查詢統計值"""
    print(f"\n{'='*60}")
    print(f"查詢資料庫: {table_name}")
    print(f"{'='*60}")

    with engine.connect() as conn:
        try:
            # 檢查表格是否存在
            exists = conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :name)"
            ), {"name": table_name}).scalar()

            if not exists:
                print(f"⚠️  表格不存在: {table_name}")
                return None

            # 基本統計
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).fetchone()
            total_rows = result[0]

            result = conn.execute(text(f"SELECT COUNT(DISTINCT date) FROM {table_name}")).fetchone()
            unique_dates = result[0]

            stats = {
                'total_rows': total_rows,
                'unique_dates': unique_dates,
            }

            # 如果有 symbol 欄位
            has_symbol = conn.execute(text(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = :name AND column_name = 'symbol'
            """), {"name": table_name}).fetchone()

            if has_symbol:
                result = conn.execute(text(f"SELECT COUNT(DISTINCT symbol) FROM {table_name}")).fetchone()
                stats['unique_symbols'] = result[0]

            # 日期範圍
            result = conn.execute(text(f"SELECT MIN(date), MAX(date) FROM {table_name}")).fetchone()
            stats['date_range'] = result

            # 針對不同表格計算特定統計值
            if table_name == 'daily_quotes':
                result = conn.execute(text(f"""
                    SELECT
                        SUM(volume)::numeric,
                        SUM(value)::numeric,
                        AVG(close)::numeric,
                        MIN(close)::numeric,
                        MAX(close)::numeric
                    FROM {table_name}
                """)).fetchone()
                stats.update({
                    'sum_volume': float(result[0]) if result[0] else 0,
                    'sum_value': float(result[1]) if result[1] else 0,
                    'avg_close': float(result[2]) if result[2] else 0,
                    'min_close': float(result[3]) if result[3] else 0,
                    'max_close': float(result[4]) if result[4] else 0,
                })
            elif table_name == 'institutional_investors':
                result = conn.execute(text(f"""
                    SELECT
                        SUM(foreign_buy)::numeric,
                        SUM(trust_buy)::numeric,
                        SUM(dealer_net)::numeric
                    FROM {table_name}
                """)).fetchone()
                if result:
                    stats['sum_foreign_buy'] = float(result[0]) if result[0] else 0
                    stats['sum_trust_buy'] = float(result[1]) if result[1] else 0
                    stats['sum_dealer_net'] = float(result[2]) if result[2] else 0
            elif table_name == 'margin_trading':
                # margin_long_balance 和 margin_short_balance 是 double precision 型別
                # SUM() 會自動忽略 NULL 值，不需要 WHERE 條件
                result = conn.execute(text(f"""
                    SELECT
                        SUM(margin_long_balance),
                        SUM(margin_short_balance)
                    FROM {table_name}
                """)).fetchone()
                if result:
                    stats['sum_margin_long_balance'] = float(result[0]) if result[0] else 0
                    stats['sum_margin_short_balance'] = float(result[1]) if result[1] else 0
            elif table_name == 'pe_ratio':
                result = conn.execute(text(f"""
                    SELECT AVG(pe_ratio)::numeric
                    FROM {table_name}
                    WHERE pe_ratio > 0 AND pe_ratio IS NOT NULL
                """)).fetchone()
                if result and result[0]:
                    stats['avg_pe_ratio'] = float(result[0])

            return stats

        except Exception as e:
            print(f"❌ 查詢失敗: {e}")
            return None


def compare_stats(csv_stats, db_stats, table_name):
    """比較 CSV 和資料庫的統計值"""
    print(f"\n{'='*60}")
    print(f"比對結果: {table_name}")
    print(f"{'='*60}")

    if not csv_stats or not db_stats:
        print("❌ 無法比對（資料不完整）")
        return False, ["資料不完整，無法比對"]

    all_match = True
    errors = []

    for key in csv_stats.keys():
        csv_val = csv_stats[key]
        db_val = db_stats.get(key)

        # 處理不同類型的比較
        if isinstance(csv_val, tuple):  # date_range
            match = csv_val == db_val
        elif isinstance(csv_val, (int, float)):
            # 浮點數容許微小誤差（0.01%）
            if csv_val == 0 and db_val == 0:
                match = True
            elif csv_val == 0 or db_val == 0:
                match = abs(csv_val - db_val) < 0.001
            else:
                diff_pct = abs(csv_val - db_val) / abs(csv_val) * 100
                match = diff_pct < 0.01
        else:
            match = csv_val == db_val

        status = "✅" if match else "❌"

        if isinstance(csv_val, float):
            print(f"{status} {key:20} | CSV: {csv_val:20,.2f} | DB: {db_val:20,.2f}")
        else:
            print(f"{status} {key:20} | CSV: {str(csv_val):20} | DB: {str(db_val):20}")

        if not match:
            all_match = False
            if isinstance(csv_val, float) and csv_val != 0:
                diff_pct = abs(csv_val - db_val) / abs(csv_val) * 100
                error_msg = f"{key}: CSV={csv_val:.2f}, DB={db_val:.2f}, 差異={diff_pct:.4f}%"
            else:
                error_msg = f"{key}: CSV={csv_val}, DB={db_val}"
            errors.append(error_msg)
            print(f"   ⚠️  {error_msg}")

    print(f"\n{'='*60}")
    if all_match:
        print(f"✅ {table_name} 驗證通過！")
    else:
        print(f"❌ {table_name} 驗證失敗，有差異！")
    print(f"{'='*60}")

    return all_match, errors


def validate_all_tables(engine):
    """驗證所有表格"""
    print("\n" + "="*60)
    print("🔍 開始統計值比對驗證...")
    print("="*60)

    # 要驗證的表格（依據 IMPORT_CATEGORY）
    import_category = os.getenv("IMPORT_CATEGORY")
    if import_category:
        tables = [import_category]
    else:
        # 只驗證主要的表格（跳過 stock_info, stock_tags 等無日期的表格）
        tables = [
            'daily_quotes',
            'institutional_investors',
            'margin_trading',
            'pe_ratio',
        ]

    results = {}
    all_errors = {}

    for table in tables:
        # 檢查是否有對應的 CSV 目錄
        csv_dir = f"/app/data/processed/{table}"
        if not os.path.exists(csv_dir):
            print(f"\n⏭️  跳過 {table}（沒有對應的 CSV 目錄）")
            continue

        try:
            csv_stats = get_csv_stats(table)
            db_stats = get_db_stats(engine, table)
            passed, errors = compare_stats(csv_stats, db_stats, table)
            results[table] = passed
            if errors:
                all_errors[table] = errors
        except Exception as e:
            print(f"\n❌ {table} 驗證時發生錯誤: {e}")
            import traceback
            traceback.print_exc()
            results[table] = False
            all_errors[table] = [f"驗證時發生錯誤: {str(e)}"]

    # 總結
    print("\n" + "="*60)
    print("📊 驗證總結")
    print("="*60)
    for table, passed in results.items():
        status = "✅ 通過" if passed else "❌ 失敗"
        print(f"{table:30} {status}")

    print("="*60)
    all_passed = all(results.values())
    if all_passed:
        print("🎉 所有表格驗證通過！")
    else:
        print("⚠️  部分表格驗證失敗，請檢查差異")
    print("="*60 + "\n")

    return all_passed, all_errors
