import os
import shutil
import argparse
import sys

def delete_shareholding_weekly_data(target_date):
    """
    Deletes processed shareholding data (weekly) for a specific date.
    """
    if len(target_date) != 8 or not target_date.isdigit():
        print(f"Error: Invalid date format '{target_date}'. Expected YYYYMMDD.")
        sys.exit(1)

    year = target_date[:4]
    
    # Get the project root directory (parent of tools/)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Target path: data/processed/shareholding/<year>/<target_date>
    path = os.path.join(base_dir, "data", "processed", "shareholding", year, target_date)
    
    print(f"--- Checking data/processed/shareholding for date {target_date} ---")
    
    if os.path.exists(path):
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
            print(f"Deleted: {path}")
            print(f"\nSuccessfully deleted shareholding data (weekly) for {target_date}.")
        except Exception as e:
            print(f"Failed to delete {path}: {e}")
    else:
        print(f"\nNo shareholding data (weekly) found for date {target_date} at: {path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete processed shareholding data (weekly) for a specific date.")
    parser.add_argument("date", help="Target date in YYYYMMDD format (e.g., 20240212)")
    
    args = parser.parse_args()
    delete_shareholding_weekly_data(args.date)
