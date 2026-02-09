import datetime
import os
from pathlib import Path

def _append_missing(title, context, missing):
    if not missing:
        return
    error_md = Path("/app/scraper_error.md")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_md, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] {title}\n")
        for line in context:
            f.write(f"{line}\n")
        f.write("Missing files:\n")
        for path in missing:
            f.write(f"- {path}\n")
    print(f"\n[WARN] Missing outputs detected. See: {error_md}")


def main():
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    year = os.getenv("REVENUE_YEAR", "").strip()
    month = os.getenv("REVENUE_MONTH", "").strip()

    if not year or not month:
        print("[INFO] REVENUE_YEAR or REVENUE_MONTH not set. Skip monthly output check.")
        return

    try:
        month_int = int(month)
    except ValueError:
        print(f"[WARN] Invalid REVENUE_MONTH: {month}. Skip monthly output check.")
        return

    date_str = f"{year}{month_int:02d}01"
    base_dir = Path(output_dir).resolve()
    target_path = base_dir / "raw" / "monthly_revenue" / f"date={date_str}" / "market.csv"

    missing = []
    if not target_path.exists() or target_path.stat().st_size == 0:
        missing.append(str(target_path))

    _append_missing(
        title="scraper-monthly missing outputs",
        context=[f"Date: {date_str}"],
        missing=missing,
    )


if __name__ == "__main__":
    main()
