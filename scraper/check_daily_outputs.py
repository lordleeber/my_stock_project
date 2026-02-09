import datetime
import os
from pathlib import Path


def _append_missing(missing, date_list, market_type):
    if not missing:
        return

    error_md = Path("/app/error_scraper_daily")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_md, "a", encoding="utf-8") as f:
        f.write(f"\n[{timestamp}] scraper-daily missing outputs\n")
        f.write(f"Market Type: {market_type}\n")
        f.write(f"Dates: {', '.join(date_list)}\n")
        f.write("Missing files:\n")
        for path in missing:
            f.write(f"- {path}\n")

    print(f"\n[WARN] Missing outputs detected. See: {error_md}")


def check_daily_outputs(date_list, output_dir, market_type):
    datasets = [
        "daily_quotes",
        "institutional_summary",
        "institutional_investors",
        "foreign_holding",
        "margin_trading",
        "margin_sbl",
        "pe_ratio",
    ]
    if market_type == "SII":
        markets = ["sii"]
    elif market_type == "OTC":
        markets = ["otc"]
    else:
        markets = ["sii", "otc"]

    base_dir = Path(output_dir).resolve()

    missing = []
    for date in date_list:
        for dataset in datasets:
            for market in markets:
                path = base_dir / "raw" / dataset / f"date={date}" / f"{market}.csv"
                if not path.exists() or path.stat().st_size == 0:
                    missing.append(str(path))

    _append_missing(missing, date_list, market_type)


if __name__ == "__main__":
    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    market_type = os.getenv("MARKET_TYPE", "ALL").upper()
    dates = os.getenv("DATE_LIST", "")
    date_list = [d for d in dates.split(",") if d]

    if not date_list:
        print("[INFO] DATE_LIST is empty. Skip daily output check.")
    else:
        check_daily_outputs(date_list, output_dir, market_type)
