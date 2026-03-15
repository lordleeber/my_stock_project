import os
import shutil
import argparse
import sys


def delete_processed_daily_data(target_date):
    """
    Deletes processed data for a specific date from the specified categories.
    """
    if len(target_date) != 8 or not target_date.isdigit():
        print(f"Error: Invalid date format '{target_date}'. Expected YYYYMMDD.")
        sys.exit(1)

    year = target_date[:4]

    # Categories specified for processed data
    processed_categories = [
        "daily_quotes",  # 每日個股行情
        "institutional_investors",  # 三大法人買賣超
        "foreign_holding",  # 外資持股
        "margin_trading",  # 融資融券
        "margin_sbl",  # 融券借券
        "pe_ratio",  # 本益比
        "market_indices",  # 大盤指數
        "institutional_summary",  # 三大法人彙總表
        "margin_summary",  # 融資融券彙總表
    ]

    # Get the project root directory (parent of tools/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    deleted_count = 0

    print(f"--- Checking data/processed for date {target_date} ---")
    for cat in processed_categories:
        # Expected structure: data/processed/<category>/<year>/<target_date>
        path = os.path.join(base_dir, "data", "processed", cat, year, target_date)

        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                print(f"Deleted: {path}")
                deleted_count += 1
            except Exception as e:
                print(f"Failed to delete {path}: {e}")

    if deleted_count == 0:
        print(f"\nNo processed data found for date {target_date}.")
    else:
        print(f"\nTotal items deleted: {deleted_count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete processed stock data for a specific date."
    )
    parser.add_argument("date", help="Target date in YYYYMMDD format (e.g., 20240212)")

    args = parser.parse_args()
    delete_processed_daily_data(args.date)
