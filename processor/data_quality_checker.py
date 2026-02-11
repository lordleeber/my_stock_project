#!/usr/bin/env python3
"""
Data Quality Checker for Processed Data

Checks processed CSV files for data quality issues and writes findings to error.md
Run after processor to catch issues before importing to database.

Usage:
    python data_quality_checker.py YYYYMMDD
    START_DATE=20260207 python data_quality_checker.py
"""

import os
import sys
import pandas as pd
from datetime import datetime
from pathlib import Path


def verify_source_lineage(df, label, limit=20):
    """
    驗證前 N 筆資料的來源追蹤資訊是否正確 (Lineage Verification)
    """
    issues = []
    if len(df) == 0:
        return issues

    # 1. 基礎欄位檢查
    for col in ["src_file", "src_row", "src_col"]:
        if col not in df.columns:
            return [f"{label}: Missing lineage column '{col}'"]
        if df[col].isna().any():
            issues.append(f"{label}: Found NULL values in lineage column '{col}'")

    # 2. 抽樣驗證 (前 N 筆)
    check_limit = min(len(df), limit)
    sample = df.head(check_limit)

    for idx, row in sample.iterrows():
        src_file = str(row['src_file'])
        try:
            src_row = int(float(row['src_row']))
        except (ValueError, TypeError):
            issues.append(f"{label} row {idx}: Invalid src_row value '{row['src_row']}'")
            continue

        # 處理路徑：如果是在 Docker 內，路徑可能是絕對路徑 /app/data/...
        # 如果是本地，可能需要調整
        full_path = Path(src_file)
        if not full_path.exists():
            # 嘗試補上當前目錄前綴或是 /app/
            if not src_file.startswith("/"):
                # 嘗試相對路徑
                cwd = Path.cwd()
                alt_path = cwd / src_file
                if not alt_path.exists():
                    # 嘗試從 my_stock_project 根目錄找
                    # 假設 data_quality_checker 在 processor/ 下
                    alt_path = cwd.parent / src_file
            
            if not alt_path.exists():
                issues.append(f"{label} row {idx}: Source file not found: {src_file}")
                continue
            full_path = alt_path

        # 取得識別資訊 (symbol 或 name)
        identity = str(row.get('symbol', row.get('name', row.get('institution', ''))))
        if not identity or identity == 'nan':
            continue

        try:
            with open(full_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                # 讀取到指定行 (src_row 是 1-based)
                line_content = None
                for i, line in enumerate(f):
                    if i == src_row - 1:
                        line_content = line
                        break
                
                if line_content is None:
                    issues.append(f"{label} row {idx}: Row {src_row} does not exist in source {full_path.name}")
                else:
                    # 簡單驗證：識別資訊應出現在原始行中
                    # 注意：原始行可能有引號、逗號等
                    clean_identity = identity.replace('=', '').replace('"', '').strip()
                    if clean_identity not in line_content:
                        issues.append(
                            f"{label} row {idx}: Lineage mismatch! "
                            f"Expected '{clean_identity}' to be in raw row {src_row}, "
                            f"but raw content was: {line_content.strip()[:100]}..."
                        )
        except Exception as e:
            issues.append(f"{label} row {idx}: Error accessing source file: {str(e)}")

    return issues


def get_processed_date_path(category, date_str, market=None):
    """取得 Processed 資料的路徑，相容新舊結構"""
    # 這些類別暫時保持 date= 結構
    if category in ("quarterly_reports", "income_statement", "balance_sheet", "cash_flow", "monthly_revenue"):
        if market:
            return Path(f"data/processed/{category}/date={date_str}/{market}.csv")
        return Path(f"data/processed/{category}/date={date_str}/all.csv")

    new_dir = Path(f"data/processed/{category}/{date_str[:4]}/{date_str}")
    old_dir = Path(f"data/processed/{category}/date={date_str}")
    
    base_dir = new_dir if new_dir.exists() else old_dir
    if market:
        return base_dir / f"{market}.csv"
    return base_dir / "all.csv"


def check_margin_trading(date_str):
    """Check margin_trading data quality - critical for trading analysis"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = get_processed_date_path("margin_trading", date_str, market)

        if not file_path.exists():
            issues.append(f"margin_trading: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"margin_trading {market}: File is empty (0 rows)")
                continue

            # Key columns that should have data
            key_columns = [
                'margin_long_buy',
                'margin_long_sell',
                'margin_long_balance',
                'margin_short_buy',
                'margin_short_sell',
                'margin_short_balance'
            ]

            for col in key_columns:
                if col not in df.columns:
                    issues.append(f"margin_trading {market}: Missing column '{col}'")
                    continue

                # Count NULL and empty strings
                null_count = df[col].isna().sum()
                null_pct = (null_count / len(df)) * 100

                # Critical: >90% NULL is abnormal (some stocks may legitimately have no margin trading)
                if null_pct > 90:
                    issues.append(
                        f"margin_trading {market}: Column '{col}' has {null_pct:.1f}% NULL values "
                        f"({null_count}/{len(df)} rows) - likely processor bug"
                    )

            # --- 新增: Lineage 驗證 ---
            issues.extend(verify_source_lineage(df, f"margin_trading {market}"))

        except Exception as e:
            issues.append(f"margin_trading {market}: Error reading file - {str(e)}")

    return issues


def check_margin_sbl(date_str):
    """Check margin_sbl (securities borrowing and lending) data quality"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = get_processed_date_path("margin_sbl", date_str, market)

        if not file_path.exists():
            issues.append(f"margin_sbl: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"margin_sbl {market}: File is empty (0 rows)")
                continue

            # Key columns for SBL
            key_columns = [
                'margin_short_balance',
                'margin_short_buy',
                'margin_short_sell'
            ]

            for col in key_columns:
                if col not in df.columns:
                    issues.append(f"margin_sbl {market}: Missing column '{col}'")
                    continue

                # Check for NULL and empty strings (data type may be text)
                if df[col].dtype == 'object':
                    empty_count = df[col].isna().sum() + (df[col] == '').sum()
                else:
                    empty_count = df[col].isna().sum()

                empty_pct = (empty_count / len(df)) * 100

                if empty_pct > 90:
                    issues.append(
                        f"margin_sbl {market}: Column '{col}' has {empty_pct:.1f}% empty values "
                        f"({empty_count}/{len(df)} rows) - likely processor bug"
                    )

            # --- 新增: Lineage 驗證 ---
            issues.extend(verify_source_lineage(df, f"margin_sbl {market}"))

        except Exception as e:
            issues.append(f"margin_sbl {market}: Error reading file - {str(e)}")

    return issues


def check_daily_quotes(date_str):
    """Check daily_quotes data quality - core OHLCV data with internal consistency checks"""
    issues = []
    
    for market in ['sii', 'otc']:
        file_path = get_processed_date_path("daily_quotes", date_str, market)

        if not file_path.exists():
            issues.append(f"daily_quotes: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"daily_quotes {market}: File is empty (0 rows)")
                continue

            # 1. 基礎欄位與 NULL 檢查
            key_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in key_columns:
                if col not in df.columns:
                    issues.append(f"daily_quotes {market}: Missing column '{col}'")
                    continue
                null_pct = (df[col].isna().sum() / len(df)) * 100
                if null_pct > 50:
                    issues.append(f"daily_quotes {market}: Column '{col}' has {null_pct:.1f}% NULLs")

            # 2. 內部 OHLC 邏輯檢查 (避免欄位位移)
            # 這是偵測數據錯位最穩健的方式，不受除權息影響
            # 例如：High 必須是當日最高點，Low 必須是當日最低點
            ohlc_err = df[
                (df['high'] < df['open']) | 
                (df['high'] < df['close']) | 
                (df['low'] > df['open']) | 
                (df['low'] > df['close'])
            ]
            if len(ohlc_err) > 0:
                issues.append(
                    f"daily_quotes {market}: Found {len(ohlc_err)} rows with invalid OHLC logic "
                    f"(e.g., high < close). This strongly suggests column shifting in raw CSV."
                )

            # --- 新增: Lineage 驗證 ---
            issues.extend(verify_source_lineage(df, f"daily_quotes {market}"))

        except Exception as e:
            issues.append(f"daily_quotes {market}: Error reading file - {str(e)}")

    return issues


def check_institutional_investors(date_str):
    """Check institutional_investors data quality"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = get_processed_date_path("institutional_investors", date_str, market)

        if not file_path.exists():
            issues.append(f"institutional_investors: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"institutional_investors {market}: File is empty (0 rows)")
                continue

            # Key columns
            key_columns = ['foreign_net', 'trust_net', 'dealer_net']

            for col in key_columns:
                if col not in df.columns:
                    issues.append(f"institutional_investors {market}: Missing column '{col}'")
                    continue

                null_count = df[col].isna().sum()
                null_pct = (null_count / len(df)) * 100

                if null_pct > 50:
                    issues.append(
                        f"institutional_investors {market}: Column '{col}' has {null_pct:.1f}% NULL values "
                        f"({null_count}/{len(df)} rows)"
                    )

            # --- 新增: Lineage 驗證 ---
            issues.extend(verify_source_lineage(df, f"institutional_investors {market}"))

        except Exception as e:
            issues.append(f"institutional_investors {market}: Error reading file - {str(e)}")

    return issues


def check_foreign_holding(date_str):
    """Check foreign_holding data quality"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = get_processed_date_path("foreign_holding", date_str, market)

        if not file_path.exists():
            issues.append(f"foreign_holding: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"foreign_holding {market}: File is empty (0 rows)")
                continue

            # Key columns for foreign shareholding
            key_columns = [
                'foreign_held_shares',
                'foreign_investable_shares',
                'foreign_held_ratio'
            ]

            for col in key_columns:
                if col not in df.columns:
                    issues.append(f"foreign_holding {market}: Missing column '{col}'")
                    continue

                null_count = df[col].isna().sum()
                null_pct = (null_count / len(df)) * 100

                # >70% NULL is suspicious for foreign holding data
                if null_pct > 70:
                    issues.append(
                        f"foreign_holding {market}: Column '{col}' has {null_pct:.1f}% NULL values "
                        f"({null_count}/{len(df)} rows)"
                    )

            # --- 新增: Lineage 驗證 ---
            issues.extend(verify_source_lineage(df, f"foreign_holding {market}"))

        except Exception as e:
            issues.append(f"foreign_holding {market}: Error reading file - {str(e)}")

    return issues


def check_pe_ratio(date_str):
    """Check pe_ratio data quality"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = get_processed_date_path("pe_ratio", date_str, market)

        if not file_path.exists():
            issues.append(f"pe_ratio: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"pe_ratio {market}: File is empty (0 rows)")
                continue

            # PE ratio column
            if 'pe_ratio' not in df.columns:
                issues.append(f"pe_ratio {market}: Missing column 'pe_ratio'")
                continue

            null_count = df['pe_ratio'].isna().sum()
            null_pct = (null_count / len(df)) * 100

            # Note: PE ratio can legitimately be NULL for many stocks (loss-making, special cases)
            # Only flag if >80% are NULL (suggests data source issue)
            if null_pct > 80:
                issues.append(
                    f"pe_ratio {market}: Column 'pe_ratio' has {null_pct:.1f}% NULL values "
                    f"({null_count}/{len(df)} rows) - may indicate data source issue"
                )

            # Check for invalid values (negative PE ratio)
            if 'pe_ratio' in df.columns:
                invalid_count = (df['pe_ratio'] < 0).sum()
                if invalid_count > 0:
                    issues.append(
                        f"pe_ratio {market}: Found {invalid_count} negative PE ratio values "
                        "(PE ratio should be positive or NULL)"
                    )

            # --- 新增: Lineage 驗證 ---
            issues.extend(verify_source_lineage(df, f"pe_ratio {market}"))

        except Exception as e:
            issues.append(f"pe_ratio {market}: Error reading file - {str(e)}")

    return issues


def check_market_indices(date_str):
    """Check market_indices data quality"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = get_processed_date_path("market_indices", date_str, market)

        if not file_path.exists():
            # SII market indices are auto-extracted from daily_quotes, so they might not exist
            # if daily_quotes extraction failed or is not applicable.
            # OTC is usually a direct raw file.
            if market == 'otc':
                issues.append(f"market_indices: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"market_indices {market}: File is empty (0 rows)")
                continue

            # Key columns for market indices
            key_columns = ['close', 'change']

            for col in key_columns:
                if col not in df.columns:
                    issues.append(f"market_indices {market}: Missing column '{col}'")
                    continue

                null_count = df[col].isna().sum()
                null_pct = (null_count / len(df)) * 100

                # Market indices should have very low NULL rate
                if null_pct > 30:
                    issues.append(
                        f"market_indices {market}: Column '{col}' has {null_pct:.1f}% NULL values "
                        f"({null_count}/{len(df)} rows)"
                    )

            # --- 新增: Lineage 驗證 ---
            issues.extend(verify_source_lineage(df, f"market_indices {market}"))

        except Exception as e:
            issues.append(f"market_indices {market}: Error reading file - {str(e)}")

    return issues


def check_monthly_revenue(date_str):
    """Check monthly_revenue data quality

    Note: Monthly revenue uses YYYYMXX directory format.
    This check converts date_str to YYYYMXX format.
    """
    issues = []

    try:
        # Convert YYYYMMDD to YYYYMXX
        year = date_str[:4]
        month = date_str[4:6]
        ym_q_str = f"{year}M{month}"

        file_path = Path(f"data/processed/monthly_revenue/date={ym_q_str}/all.csv")

        if not file_path.exists():
            # Monthly revenue is optional (only available after 10th of each month)
            # Don't flag as error if file doesn't exist
            return issues

        df = pd.read_csv(file_path)

        if len(df) == 0:
            issues.append(f"monthly_revenue {ym_q_str}: File is empty (0 rows)")
            return issues

        # Check date format (should be YYYYMXX)
        if 'date' in df.columns:
            import re
            invalid_dates = df[~df['date'].astype(str).str.match(r'^\d{4}M\d{2}$')]
            if len(invalid_dates) > 0:
                issues.append(
                    f"monthly_revenue {ym_q_str}: Found {len(invalid_dates)} rows with invalid date format "
                    f"(expected YYYYMXX, e.g., 2025M01)"
                )

        # Key columns for revenue
        key_columns = [
            'revenue_current',
            'mom_pct',
            'yoy_pct'
        ]

        for col in key_columns:
            if col not in df.columns:
                issues.append(f"monthly_revenue {ym_str}: Missing column '{col}'")
                continue

            null_count = df[col].isna().sum()
            null_pct = (null_count / len(df)) * 100

            # Revenue data can have some NULL (not all companies report monthly)
            if null_pct > 60:
                issues.append(
                    f"monthly_revenue {ym_str}: Column '{col}' has {null_pct:.1f}% NULL values "
                    f"({null_count}/{len(df)} rows)"
                )

    except Exception as e:
        issues.append(f"monthly_revenue: Error reading file - {str(e)}")

    return issues


def check_shareholding_div(date_str):
    """Check shareholding_div (TDCC) data quality"""
    issues = []

    file_path = get_processed_date_path("shareholding_div", date_str)

    if not file_path.exists():
        # TDCC data is weekly, so it's normal for most dates to not have data
        # Don't flag as error if file doesn't exist
        return issues

    try:
        df = pd.read_csv(file_path)

        if len(df) == 0:
            issues.append(f"shareholding_div: File is empty (0 rows)")
            return issues

        # Key columns for shareholding dispersion
        key_columns = [
            'holders',
            'shares',
            'percentage'
        ]

        for col in key_columns:
            if col not in df.columns:
                issues.append(f"shareholding_div: Missing column '{col}'")
                continue

            null_count = df[col].isna().sum()
            null_pct = (null_count / len(df)) * 100

            # Shareholding data should have low NULL rate
            if null_pct > 50:
                issues.append(
                    f"shareholding_div: Column '{col}' has {null_pct:.1f}% NULL values "
                    f"({null_count}/{len(df)} rows)"
                )

    except Exception as e:
        issues.append(f"shareholding_div: Error reading file - {str(e)}")

    return issues


def check_institutional_summary(date_str):
    """Check institutional_summary data quality"""
    issues = []

    file_path = get_processed_date_path("institutional_summary", date_str)

    if not file_path.exists():
        issues.append(f"institutional_summary: Missing file {file_path}")
        return issues

    try:
        df = pd.read_csv(file_path)

        if len(df) == 0:
            issues.append(f"institutional_summary: File is empty (0 rows)")
            return issues

        # Key columns for institutional summary
        key_columns = ['buy', 'sell', 'net']

        for col in key_columns:
            if col not in df.columns:
                issues.append(f"institutional_summary: Missing column '{col}'")
                continue

            null_count = df[col].isna().sum()
            null_pct = (null_count / len(df)) * 100

            # Institutional summary should have no NULL values
            if null_pct > 10:
                issues.append(
                    f"institutional_summary: Column '{col}' has {null_pct:.1f}% NULL values "
                    f"({null_count}/{len(df)} rows)"
                )

        # Check that we have data for major institution types
        if 'institution' in df.columns:
            institutions = df['institution'].unique()
            expected_institutions = ['foreign', 'trust', 'dealer']

            for inst in expected_institutions:
                if not any(inst in str(i).lower() for i in institutions):
                    issues.append(
                        f"institutional_summary: Missing expected institution type '{inst}'"
                    )

    except Exception as e:
        issues.append(f"institutional_summary: Error reading file - {str(e)}")

    return issues


def write_error_report(date_str, issues):
    """Write error report to root error_processor.md file"""
    if not issues:
        return

    error_file = Path("/app/error_processor.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build report
    report = f"\n## Data Quality Issues - {date_str}\n"
    report += f"**Detected at:** {timestamp}\n"
    report += f"**Issue count:** {len(issues)}\n\n"

    for issue in issues:
        report += f"- ❌ {issue}\n"

    report += "\n**Action required:**\n"
    report += "1. Check raw data files in `data/raw/*/`\n"
    report += "2. Review processor logs for errors\n"
    report += "3. Fix processor bugs if column mapping is incorrect\n"
    report += "4. Re-run processor: `START_DATE=" + date_str + " END_DATE=" + date_str + " docker compose run --rm processor`\n"
    report += "\n---\n"

    # Append to error_processor.md (create if not exists)
    with open(error_file, 'a', encoding='utf-8') as f:
        f.write(report)

    print(f"\n⚠️  Found {len(issues)} data quality issues for {date_str}")
    print(f"📝 Report written to error_processor.md")


def main():
    # Get date from environment variable or command line
    date_str = os.getenv('START_DATE')

    if not date_str and len(sys.argv) > 1:
        date_str = sys.argv[1]

    if not date_str:
        print("Error: Please provide date via START_DATE env var or command line argument")
        print("Usage: python data_quality_checker.py YYYYMMDD")
        print("   or: START_DATE=20260207 python data_quality_checker.py")
        sys.exit(1)

    # Validate date format
    try:
        datetime.strptime(date_str, '%Y%m%d')
    except ValueError:
        print(f"Error: Invalid date format '{date_str}'. Expected YYYYMMDD")
        sys.exit(1)

    print(f"🔍 Checking data quality for {date_str}...")
    print(f"📂 Processed data directory: data/processed/")
    print()

    all_issues = []

    # Run all checks
    print("Checking margin_trading...")
    all_issues.extend(check_margin_trading(date_str))

    print("Checking margin_sbl...")
    all_issues.extend(check_margin_sbl(date_str))

    print("Checking daily_quotes...")
    all_issues.extend(check_daily_quotes(date_str))

    print("Checking institutional_investors...")
    all_issues.extend(check_institutional_investors(date_str))

    print("Checking foreign_holding...")
    all_issues.extend(check_foreign_holding(date_str))

    print("Checking pe_ratio...")
    all_issues.extend(check_pe_ratio(date_str))

    print("Checking market_indices...")
    all_issues.extend(check_market_indices(date_str))

    print("Checking monthly_revenue...")
    all_issues.extend(check_monthly_revenue(date_str))

    print("Checking shareholding_div...")
    all_issues.extend(check_shareholding_div(date_str))

    print("Checking institutional_summary...")
    all_issues.extend(check_institutional_summary(date_str))

    # Write report if issues found
    if all_issues:
        write_error_report(date_str, all_issues)
        print("\n❌ Data quality check FAILED")
        sys.exit(1)
    else:
        print("\n✅ All data quality checks passed!")
        sys.exit(0)


if __name__ == '__main__':
    main()
