import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.error_log import append_error_log  # noqa: E402

ERROR_LOG = "error_scraper.log"


def _append_missing(title, context, missing):
    if not missing:
        return
    lines = list(context) + ["Missing files:"] + [f"- {p}" for p in missing]
    append_error_log(ERROR_LOG, title, lines)


def check_monthly_outputs(output_dir, year, month):
    month_int = int(month)
    date_str = f"{year}{month_int:02d}01"
    base_dir = Path(output_dir).resolve()

    missing = []
    new_dir = (
        base_dir
        / "raw"
        / "monthly_revenue"
        / date_str[:4]
        / f"{date_str[:4]}M{date_str[4:6]}"
    )
    required_files = [new_dir / "tmp.csv", new_dir / "market.csv"]
    for p in required_files:
        if not p.exists() or p.stat().st_size == 0:
            missing.append(str(p))

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
        print(
            "[INFO] REVENUE_YEAR or REVENUE_MONTH not set. Skip monthly output check."
        )
    else:
        try:
            check_monthly_outputs(output_dir, year, month)
        except ValueError:
            print(f"[WARN] Invalid REVENUE_MONTH: {month}. Skip monthly output check.")
