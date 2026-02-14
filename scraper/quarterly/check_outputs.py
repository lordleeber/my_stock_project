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


def _market_files(target_dir, market):
    return list(Path(target_dir).glob(f"{market}_*.csv"))


def check_quarterly_outputs(output_dir, year, quarter):
    date_str = f"{year}Q{quarter}"
    base_dir = Path(output_dir).resolve()

    datasets = [
        "income_statement",
        "balance_sheet",
        "cash_flow",
    ]

    missing = []

    # reports raw csv/xls
    reports_dir = base_dir / "raw" / "quarterly_reports" / str(year) / date_str
    for market in ("sii", "otc"):
        if not (reports_dir / f"{market}.csv").exists():
            missing.append(str(reports_dir / f"{market}.csv"))

    # statements
    for dataset in datasets:
        target_dir = base_dir / "raw" / dataset / str(year) / date_str
        if not target_dir.exists():
            missing.append(str(target_dir))
            continue
        for market in ("sii", "otc"):
            files = _market_files(target_dir, market)
            if not files:
                missing.append(str(target_dir / f"{market}_*.csv"))

    _append_missing(
        title="scraper-quarterly missing outputs",
        context=[f"Date: {date_str}"],
        missing=missing,
    )


if __name__ == "__main__":
    import os

    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    year = os.getenv("REPORT_YEAR", "").strip()
    quarter = os.getenv("REPORT_QUARTER", "").strip()

    if not year or not quarter:
        print("[INFO] REPORT_YEAR or REPORT_QUARTER not set. Skip quarterly output check.")
    else:
        check_quarterly_outputs(output_dir, year, quarter)
