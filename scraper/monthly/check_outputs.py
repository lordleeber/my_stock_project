import datetime
from pathlib import Path


def _append_missing(title, context, missing):
    if not missing:
        return
    error_md = Path("/app/error_scraper.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_md, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] {title}\n")
        for line in context:
            f.write(f"{line}\n")
        f.write("Missing files:\n")
        for path in missing:
            f.write(f"- {path}\n")
    print(f"\n[WARN] Missing outputs detected. See: {error_md}")


def check_monthly_outputs(output_dir, year, month):
    month_int = int(month)
    date_str = f"{year}{month_int:02d}01"
    base_dir = Path(output_dir).resolve()

    # Prefer new path, fallback old path
    new_path = base_dir / "raw" / "monthly_revenue" / date_str[:4] / f"{date_str[:4]}M{date_str[4:6]}" / "market.csv"
    old_path = base_dir / "raw" / "monthly_revenue" / f"date={date_str}" / "market.csv"
    target_path = new_path if new_path.exists() else old_path

    missing = []
    if not target_path.exists() or target_path.stat().st_size == 0:
        missing.append(str(target_path))

    _append_missing(
        title="scraper-monthly missing outputs",
        context=[f"Date: {date_str}"],
        missing=missing,
    )


if __name__ == "__main__":
    import os

    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    year = os.getenv("REVENUE_YEAR", "").strip()
    month = os.getenv("REVENUE_MONTH", "").strip()

    if not year or not month:
        print("[INFO] REVENUE_YEAR or REVENUE_MONTH not set. Skip monthly output check.")
    else:
        try:
            check_monthly_outputs(output_dir, year, month)
        except ValueError:
            print(f"[WARN] Invalid REVENUE_MONTH: {month}. Skip monthly output check.")
