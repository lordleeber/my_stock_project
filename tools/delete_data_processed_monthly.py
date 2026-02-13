import os
import shutil
import argparse
import sys

def delete_processed_monthly_data(target_date):
    """
    Deletes processed monthly revenue data for a specific date (YYYYMMDD).
    Note: Monthly data typically uses the 1st of the month or a specific date as the folder name.
    """
    if len(target_date) != 8 or not target_date.isdigit():
        print(f"Error: Invalid date format '{target_date}'. Expected YYYYMMDD.")
        sys.exit(1)

    year = target_date[:4]
    
    # Get the project root directory (parent of tools/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Target path: data/processed/monthly_revenue/<year>/<target_date>
    path = os.path.join(base_dir, "data", "processed", "monthly_revenue", year, target_date)
    
    print(f"--- Checking data/processed/monthly_revenue for date {target_date} ---")
    
    if os.path.exists(path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            print(f"Deleted: {path}")
            print(f"\nSuccessfully deleted monthly revenue data for {target_date}.")
        except Exception as e:
            print(f"Failed to delete {path}: {e}")
    else:
        print(f"\nNo monthly revenue data found for date {target_date} at: {path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete processed monthly revenue data for a specific date.")
    parser.add_argument("date", help="Target date in YYYYMMDD format (e.g., 20240201)")
    
    args = parser.parse_args()
    delete_processed_monthly_data(args.date)
