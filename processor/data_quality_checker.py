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


def check_margin_trading(date_str):
    """Check margin_trading data quality - critical for trading analysis"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = Path(f"data/processed/margin_trading/date={date_str}/{market}.csv")

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

        except Exception as e:
            issues.append(f"margin_trading {market}: Error reading file - {str(e)}")

    return issues


def check_margin_sbl(date_str):
    """Check margin_sbl (securities borrowing and lending) data quality"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = Path(f"data/processed/margin_sbl/date={date_str}/{market}.csv")

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

        except Exception as e:
            issues.append(f"margin_sbl {market}: Error reading file - {str(e)}")

    return issues


def check_daily_quotes(date_str):
    """Check daily_quotes data quality - core OHLCV data"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = Path(f"data/processed/daily_quotes/date={date_str}/{market}.csv")

        if not file_path.exists():
            issues.append(f"daily_quotes: Missing file {file_path}")
            continue

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                issues.append(f"daily_quotes {market}: File is empty (0 rows)")
                continue

            # Core OHLCV columns
            key_columns = ['open', 'high', 'low', 'close', 'volume']

            for col in key_columns:
                if col not in df.columns:
                    issues.append(f"daily_quotes {market}: Missing column '{col}'")
                    continue

                null_count = df[col].isna().sum()
                null_pct = (null_count / len(df)) * 100

                # >50% NULL in OHLCV is suspicious (some NULL is OK for suspended stocks)
                if null_pct > 50:
                    issues.append(
                        f"daily_quotes {market}: Column '{col}' has {null_pct:.1f}% NULL values "
                        f"({null_count}/{len(df)} rows) - check if market was open"
                    )

        except Exception as e:
            issues.append(f"daily_quotes {market}: Error reading file - {str(e)}")

    return issues


def check_institutional_investors(date_str):
    """Check institutional_investors data quality"""
    issues = []

    for market in ['sii', 'otc']:
        file_path = Path(f"data/processed/institutional_investors/date={date_str}/{market}.csv")

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

        except Exception as e:
            issues.append(f"institutional_investors {market}: Error reading file - {str(e)}")

    return issues


def write_error_report(date_str, issues):
    """Write error report to root error.md file"""
    if not issues:
        return

    error_file = Path("error.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build report
    report = f"\n## Data Quality Issues - {date_str}\n"
    report += f"**Detected at:** {timestamp}\n"
    report += f"**Issue count:** {len(issues)}\n\n"

    for issue in issues:
        report += f"- ❌ {issue}\n"

    report += "\n**Action required:**\n"
    report += "1. Check raw data files in `data/raw/*/date=" + date_str + "/`\n"
    report += "2. Review processor logs for errors\n"
    report += "3. Fix processor bugs if column mapping is incorrect\n"
    report += "4. Re-run processor: `START_DATE=" + date_str + " END_DATE=" + date_str + " docker compose run --rm processor`\n"
    report += "\n---\n"

    # Append to error.md (create if not exists)
    with open(error_file, 'a', encoding='utf-8') as f:
        f.write(report)

    print(f"\n⚠️  Found {len(issues)} data quality issues for {date_str}")
    print(f"📝 Report written to error.md")


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
