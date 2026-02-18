#!/usr/bin/env python3
import csv
from pathlib import Path


ROOT = Path("data/raw/monthly_revenue")


def publish_date_from_month_key(month_key: str) -> str:
    # month_key format: YYYYMXX, e.g. 2020M01
    year = int(month_key[:4])
    month = int(month_key[5:7])
    if month == 12:
        return f"{year + 1}0110"
    return f"{year}{month + 1:02d}10"


def process_file(path: Path) -> bool:
    month_key = path.parent.name
    if len(month_key) != 7 or month_key[4] != "M":
        raise ValueError(f"Unexpected month directory format: {path}")

    publish_date = publish_date_from_month_key(month_key)

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"Missing header: {path}")
        fieldnames = list(reader.fieldnames)
        rows = list(reader)

    changed = False
    # Normalize header to publish_time only.
    if "publish_date" in fieldnames:
        idx = fieldnames.index("publish_date")
        fieldnames[idx] = "publish_time"
        changed = True
    if "publish_time" not in fieldnames:
        fieldnames.append("publish_time")
        changed = True

    for row in rows:
        if row.get("publish_time") != publish_date:
            row["publish_time"] = publish_date
            changed = True
        # Remove legacy key if present
        if "publish_date" in row:
            row.pop("publish_date", None)
            changed = True

    if changed:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    return changed


def main() -> None:
    files = sorted(ROOT.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9][0-9][0-9]M[0-9][0-9]/market.csv"))
    if not files:
        print("No market.csv files found.")
        return

    changed_count = 0
    for file_path in files:
        if process_file(file_path):
            changed_count += 1

    print(f"Processed {len(files)} files, updated {changed_count} files.")


if __name__ == "__main__":
    main()
