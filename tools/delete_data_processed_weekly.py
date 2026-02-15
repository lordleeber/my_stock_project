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
    
    # New target path: data/processed/shareholding/<year>/<target_date>.csv
    csv_path = os.path.join(base_dir, "data", "processed", "shareholding", year, f"{target_date}.csv")
    # Legacy target path (kept for backward compatibility)
    legacy_dir_path = os.path.join(base_dir, "data", "processed", "shareholding", year, target_date)
    
    print(f"--- Checking data/processed/shareholding for date {target_date} ---")

    deleted_any = False

    if os.path.exists(csv_path):
        try:
            os.remove(csv_path)
            print(f"Deleted: {csv_path}")
            deleted_any = True
        except Exception as e:
            print(f"Failed to delete {csv_path}: {e}")

    if os.path.exists(legacy_dir_path):
        try:
            if os.path.isdir(legacy_dir_path):
                shutil.rmtree(legacy_dir_path)
            else:
                os.remove(legacy_dir_path)
            print(f"Deleted legacy path: {legacy_dir_path}")
            deleted_any = True
        except Exception as e:
            print(f"Failed to delete legacy path {legacy_dir_path}: {e}")

    if deleted_any:
        print(f"\nSuccessfully deleted shareholding data (weekly) for {target_date}.")
    else:
        print(
            f"\nNo shareholding data (weekly) found for date {target_date}. "
            f"Checked: {csv_path} and {legacy_dir_path}"
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete processed shareholding data (weekly) for a specific date.")
    parser.add_argument("date", help="Target date in YYYYMMDD format (e.g., 20240212)")
    
    args = parser.parse_args()
    delete_shareholding_weekly_data(args.date)
