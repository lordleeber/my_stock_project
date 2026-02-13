import os
import shutil
import argparse
import sys

def delete_processed_quarterly_data(target_date):
    """
    Deletes processed quarterly data for a specific date (YYYYMMDD).
    Handles both quarterly_reports and quarterly_statements.
    """
    if len(target_date) != 8 or not target_date.isdigit():
        print(f"Error: Invalid date format '{target_date}'. Expected YYYYMMDD.")
        sys.exit(1)

    year = target_date[:4]
    
    # Categories for quarterly data
    quarterly_categories = [
        "quarterly_reports",
        "quarterly_statements"
    ]

    # Get the project root directory (parent of tools/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    deleted_count = 0

    print(f"--- Checking data/processed for quarterly date {target_date} ---")
    for cat in quarterly_categories:
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
        print(f"
No quarterly data found for date {target_date}.")
    else:
        print(f"
Total quarterly items deleted: {deleted_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete processed quarterly stock data for a specific date.")
    parser.add_argument("date", help="Target date in YYYYMMDD format (e.g., 20240331)")
    
    args = parser.parse_args()
    delete_processed_quarterly_data(args.date)
