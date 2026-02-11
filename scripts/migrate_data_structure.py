#!/usr/bin/env python3
import os
import shutil
import re
from pathlib import Path

def migrate_dir(base_dir):
    base_path = Path(base_dir)
    if not base_path.exists():
        print(f"Skipping {base_dir} (not found)")
        return

    print(f"Migrating {base_dir}...")
    date_pattern = re.compile(r'^date=(\d{8})$')
    
    # Iterate over categories
    for cat_dir in base_path.iterdir():
        if not cat_dir.is_dir():
            continue
            
        # Skip categories that should keep date= (monthly revenue, quarterly reports)
        if cat_dir.name in ("quarterly_reports", "income_statement", "balance_sheet", "cash_flow", "monthly_revenue"):
            print(f"  Skipping category {cat_dir.name} (keeps date= format)")
            continue
            
        print(f"  Processing category: {cat_dir.name}")
        
        # Find date=YYYYMMDD directories
        for date_dir in cat_dir.iterdir():
            if not date_dir.is_dir():
                continue
                
            match = date_pattern.match(date_dir.name)
            if match:
                date_str = match.group(1)
                year = date_str[:4]
                
                new_parent = cat_dir / year
                new_parent.mkdir(exist_ok=True)
                
                new_dst = new_parent / date_str
                
                if new_dst.exists():
                    print(f"    ⚠️ Destination already exists: {new_dst}, merging files...")
                    # Merge files if destination exists
                    for item in date_dir.iterdir():
                        target_file = new_dst / item.name
                        if target_file.exists():
                            print(f"      ⚠️ File already exists, skipping: {item.name}")
                        else:
                            shutil.move(str(item), str(target_file))
                    
                    # If directory is now empty, remove it
                    if not any(date_dir.iterdir()):
                        date_dir.rmdir()
                    else:
                        print(f"      ⚠️ Source directory {date_dir.name} not empty after merge, keeping it.")
                else:
                    print(f"    Moving {date_dir.name} -> {year}/{date_str}")
                    shutil.move(str(date_dir), str(new_dst))

if __name__ == "__main__":
    # Migrate raw data
    migrate_dir("data/raw")
    # Migrate processed data
    migrate_dir("data/processed")
    print("Migration completed!")
