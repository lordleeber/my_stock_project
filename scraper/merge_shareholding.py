#!/usr/bin/env python3
"""
Merge shareholding_div per-stock files into shareholding all-in-one format

Usage:
    python merge_shareholding.py [--date YYYYMMDD] [--all]

Examples:
    # Merge a specific date
    python merge_shareholding.py --date 20230915

    # Merge all dates in shareholding_div
    python merge_shareholding.py --all

Output:
    Merged files will be saved to data/raw/shareholding/YYYY/TDCC_OD_1-5_YYYYMMDD.csv
"""

import os
import sys
import argparse
import csv
from pathlib import Path

# Get project root directory (assuming script is in scraper/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RAW_DIR = os.getenv("RAW_DIR", str(PROJECT_ROOT / "data" / "raw"))
INPUT_DIR = f"{RAW_DIR}/shareholding_div"
OUTPUT_DIR = f"{RAW_DIR}/shareholding"


def merge_date(date_str):
    """
    Merge all stock files for a specific date into a single TDCC format file

    Args:
        date_str: Date in YYYYMMDD format
    """
    input_date_dir = f"{INPUT_DIR}/date={date_str}"

    if not os.path.exists(input_date_dir):
        print(f"❌ Input directory not found: {input_date_dir}")
        return False

    # Get all CSV files in the date directory
    csv_files = [f for f in os.listdir(input_date_dir) if f.endswith('.csv')]

    if not csv_files:
        print(f"⚠️  No CSV files found in {input_date_dir}")
        return False

    print(f"Processing {date_str}: {len(csv_files)} stocks...")

    # Create output directory if not exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    year_dir = Path(OUTPUT_DIR) / date_str[:4]
    year_dir.mkdir(parents=True, exist_ok=True)
    output_file = year_dir / f"TDCC_OD_1-5_{date_str}.csv"

    all_rows = []
    processed_stocks = 0

    # Process each stock file
    for csv_file in sorted(csv_files):
        symbol = csv_file.replace('.csv', '')
        file_path = os.path.join(input_date_dir, csv_file)

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Skip header rows or invalid rows
                    if not row.get('持股分級'):
                        continue

                    # Convert shareholding_div format to shareholding_div2 format
                    # Input:  序,持股分級,人數,股數,占集保庫存數比例(%)
                    # Output: 資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%

                    level = row.get('持股分級', '').strip()
                    holders = row.get('人數', '').strip().replace(',', '')
                    shares = row.get('股數', '').strip().replace(',', '')
                    percentage = row.get('占集保庫存數比例(%)', '').strip()

                    # Map holding level to level code (1-9 or more)
                    # shareholding_div uses text like "1-999", "1,000-5,000"
                    # shareholding_div2 uses numeric level 1, 2, 3...
                    level_code = get_level_code(level)

                    if level_code and holders and shares:
                        all_rows.append({
                            '資料日期': date_str,
                            '證券代號': symbol,
                            '持股分級': level_code,
                            '人數': holders,
                            '股數': shares,
                            '占集保庫存數比例%': percentage
                        })

            processed_stocks += 1

        except Exception as e:
            print(f"⚠️  Error processing {symbol}: {e}")
            continue

    # Write merged data to output file
    if all_rows:
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            fieldnames = ['資料日期', '證券代號', '持股分級', '人數', '股數', '占集保庫存數比例%']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"✓ Created {output_file}")
        print(f"  Processed: {processed_stocks} stocks, {len(all_rows)} rows")
        return True
    else:
        print(f"❌ No valid data to write for {date_str}")
        return False


def get_level_code(level_text):
    """
    Map holding level text to level code

    Examples:
        "1-999" → 1
        "1,000-5,000" → 2
        "5,001-10,000" → 3
        ...
    """
    if not level_text:
        return None

    # Standard TDCC level mapping
    level_mapping = {
        '1-999': 1,
        '1,000-5,000': 2,
        '5,001-10,000': 3,
        '10,001-15,000': 4,
        '15,001-20,000': 5,
        '20,001-30,000': 6,
        '30,001-40,000': 7,
        '40,001-50,000': 8,
        '50,001-100,000': 9,
        '100,001-200,000': 10,
        '200,001-400,000': 11,
        '400,001-600,000': 12,
        '600,001-800,000': 13,
        '800,001-1,000,000': 14,
        '1,000,001以上': 15,
    }

    # Remove spaces and normalize commas
    normalized = level_text.strip().replace(' ', '')

    return level_mapping.get(normalized, None)


def main():
    parser = argparse.ArgumentParser(
        description='Merge shareholding_div per-stock files into shareholding all-in-one format'
    )
    parser.add_argument('--date', help='Specific date to merge (YYYYMMDD)')
    parser.add_argument('--all', action='store_true', help='Merge all dates in shareholding_div')

    args = parser.parse_args()

    if args.all:
        # Get all date directories
        if not os.path.exists(INPUT_DIR):
            print(f"❌ Input directory not found: {INPUT_DIR}")
            return 1

        date_dirs = [d for d in os.listdir(INPUT_DIR) if d.startswith('date=')]

        if not date_dirs:
            print(f"⚠️  No date directories found in {INPUT_DIR}")
            return 1

        print(f"Found {len(date_dirs)} dates to process")

        success_count = 0
        for date_dir in sorted(date_dirs):
            date_str = date_dir.replace('date=', '')
            if merge_date(date_str):
                success_count += 1

        print(f"\n✅ Completed: {success_count}/{len(date_dirs)} dates processed successfully")

    elif args.date:
        if not merge_date(args.date):
            return 1
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
