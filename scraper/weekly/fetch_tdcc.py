#!/usr/bin/env python3
"""
Fetch TDCC shareholding distribution data from OpenData API

This script fetches the latest shareholding distribution data from TDCC's
OpenData platform and saves it to data/raw/shareholding/YYYY/ directory.

API Endpoint: https://opendata.tdcc.com.tw/getOD.ashx?id=1-5

Output Format: TDCC_OD_1-5_{YYYYMMDD}.csv

Usage:
    python fetch_tdcc.py [--date YYYYMMDD] [--output-dir PATH]

Examples:
    # Fetch latest data (date will be auto-detected from API response)
    python fetch_tdcc.py

    # Specify custom output directory
    python fetch_tdcc.py --output-dir /path/to/output

Environment Variables:
    RAW_DIR: Base directory for raw data (default: ../data/raw)
    TDCC_DATE: Force specific date in YYYYMMDD format (optional)
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# TDCC OpenData API endpoint
TDCC_API_URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"

# Get project root directory (assuming script is in scraper/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
RAW_DIR = os.getenv("RAW_DIR", str(PROJECT_ROOT / "data" / "raw"))
OUTPUT_DIR = f"{RAW_DIR}/shareholding"


def fetch_tdcc_data(verify_ssl=True):
    """
    Fetch TDCC shareholding data from OpenData API using curl

    Args:
        verify_ssl: Whether to verify SSL certificate (default: True)

    Returns:
        tuple: (data_content, date_str) or (None, None) if failed
    """
    try:
        print(f"Fetching TDCC data from {TDCC_API_URL}...")

        # Build curl command
        curl_cmd = ["curl", "-s", "-L"]  # -s: silent, -L: follow redirects

        if not verify_ssl:
            print("⚠️  SSL verification disabled")
            curl_cmd.append("-k")  # -k: insecure (skip SSL verification)

        curl_cmd.append(TDCC_API_URL)

        # Execute curl command
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            print(f"❌ curl failed with exit code {result.returncode}")
            if result.stderr:
                print(f"Error: {result.stderr}")
            return None, None

        # Get the data
        data = result.stdout

        # Check if response is empty
        if not data:
            print("❌ API returned empty response")
            return None, None

        # Extract date from first data row
        # Format: 資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%
        #         20260206,000218,1,0,0,0.00
        lines = data.strip().split("\n")

        if len(lines) < 2:
            print("❌ API response has insufficient data")
            return None, None

        # Skip header and get first data row
        first_data_row = lines[1]
        date_str = first_data_row.split(",")[0]

        # Validate date format (YYYYMMDD)
        if len(date_str) != 8 or not date_str.isdigit():
            print(f"❌ Invalid date format in API response: {date_str}")
            return None, None

        print(f"✓ Data fetched successfully (Date: {date_str})")
        return data, date_str

    except subprocess.TimeoutExpired:
        print("❌ Request timed out after 30 seconds")
        return None, None
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return None, None


def save_data(data, date_str, output_dir):
    """
    Save fetched data to file

    Args:
        data: CSV data content
        date_str: Date in YYYYMMDD format
        output_dir: Output directory path

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create output directory if not exists
        os.makedirs(output_dir, exist_ok=True)

        # Generate output filename
        year_dir = Path(output_dir) / date_str[:4]
        year_dir.mkdir(parents=True, exist_ok=True)
        output_file = year_dir / f"TDCC_OD_1-5_{date_str}.csv"

        # Check if file already exists
        if os.path.exists(output_file):
            print(f"⚠️  File already exists: {output_file}")
            response = input("Overwrite? (y/n): ").lower()
            if response != "y":
                print("❌ Aborted by user")
                return False

        # Write data to file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(data)

        # Get file size
        file_size = os.path.getsize(output_file)
        file_size_mb = file_size / (1024 * 1024)

        # Count rows
        row_count = len(data.strip().split("\n")) - 1  # Exclude header

        print(f"✓ Data saved to: {output_file}")
        print(f"  File size: {file_size_mb:.2f} MB")
        print(f"  Total rows: {row_count:,}")

        return True

    except Exception as e:
        print(f"❌ Failed to save data: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Fetch TDCC shareholding distribution data from OpenData API"
    )
    parser.add_argument(
        "--date",
        help="Force specific date (YYYYMMDD). If not provided, date will be auto-detected from API response",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help=f"Output directory base (default: {OUTPUT_DIR}, year subfolder will be used)",
    )
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Skip overwrite prompt (always overwrite)",
    )
    parser.add_argument(
        "--no-verify", action="store_true", help="Disable SSL certificate verification"
    )

    args = parser.parse_args()

    # Override date from environment variable if set
    force_date = os.getenv("TDCC_DATE") or args.date

    # Fetch data from API
    data, detected_date = fetch_tdcc_data(verify_ssl=not args.no_verify)

    if not data:
        print("❌ Failed to fetch data")
        return 1

    # Use forced date if provided, otherwise use detected date
    date_str = force_date or detected_date

    if force_date and force_date != detected_date:
        print(f"⚠️  Using forced date {force_date} (API has data for {detected_date})")

    # Save data
    if args.no_prompt:
        # Auto-overwrite mode for automation
        year_dir = Path(args.output_dir) / date_str[:4]
        year_dir.mkdir(parents=True, exist_ok=True)
        output_file = year_dir / f"TDCC_OD_1-5_{date_str}.csv"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(data)
        file_size = os.path.getsize(output_file)
        file_size_mb = file_size / (1024 * 1024)
        row_count = len(data.strip().split("\n")) - 1
        print(f"✓ Data saved to: {output_file}")
        print(f"  File size: {file_size_mb:.2f} MB")
        print(f"  Total rows: {row_count:,}")
        return 0
    else:
        if save_data(data, date_str, args.output_dir):
            return 0
        else:
            return 1


if __name__ == "__main__":
    sys.exit(main())
