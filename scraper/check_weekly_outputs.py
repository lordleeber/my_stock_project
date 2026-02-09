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
    tdcc_date = os.getenv("TDCC_DATE", "").strip()
    stocks_file = os.getenv("TDCC_STOCKS_FILE", "/app/active_stocks.txt")

    if not tdcc_date:
        print("[INFO] TDCC_DATE not set. Skip weekly output check.")
        return

    if not Path(stocks_file).exists():
        print(f"[WARN] Stocks file not found: {stocks_file}. Skip weekly output check.")
        return

    with open(stocks_file, "r", encoding="utf-8") as f:
        stocks = [line.strip() for line in f if line.strip()]

    base_dir = Path(output_dir).resolve()
    target_dir = base_dir / "raw" / "shareholding_div" / f"date={tdcc_date}"

    missing = []
    for stock in stocks:
        path = target_dir / f"{stock}.csv"
        if not path.exists() or path.stat().st_size == 0:
            missing.append(str(path))

    _append_missing(
        title="scraper-weekly missing outputs",
        context=[
            f"Date: {tdcc_date}",
            f"Stocks file: {stocks_file}",
        ],
        missing=missing,
    )


if __name__ == "__main__":
    main()
