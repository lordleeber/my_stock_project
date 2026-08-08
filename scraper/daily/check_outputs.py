import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.error_log import append_error_log  # noqa: E402

ERROR_LOG = "error_scraper.log"


def _append_missing(missing, date_list, market_type):
    if not missing:
        return

    append_error_log(
        ERROR_LOG,
        "scraper-daily missing outputs",
        [
            f"Market Type: {market_type}",
            f"Dates: {', '.join(date_list)}",
            "Missing files:",
        ]
        + [f"- {p}" for p in missing],
    )


def _is_file_valid(path: Path, min_bytes: int, min_lines: int) -> bool:
    if not path.exists():
        return False
    try:
        if path.stat().st_size < min_bytes:
            return False
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            lines = 0
            for _ in f:
                lines += 1
                if lines >= min_lines:
                    return True
        return False
    except OSError:
        return False


def check_daily_outputs(date_list, output_dir, market_type):
    datasets = [
        "daily_quotes",
        "institutional_summary",
        "institutional_investors",
        "foreign_holding",
        "margin_trading",
        "margin_sbl",
        "pe_ratio",
        "market_indices",
    ]
    if market_type == "SII":
        markets = ["sii"]
    elif market_type == "OTC":
        markets = ["otc"]
    else:
        markets = ["sii", "otc"]

    base_dir = Path(output_dir).resolve()

    missing = []
    min_bytes = int(os.getenv("MIN_BYTES", "10"))
    min_lines = int(os.getenv("MIN_LINES", "2"))
    for date in date_list:
        for dataset in datasets:
            dataset_markets = ["otc"] if dataset == "market_indices" else markets
            for market in dataset_markets:
                new_path = (
                    base_dir / "raw" / dataset / date[:4] / date / f"{market}.csv"
                )
                old_path = base_dir / "raw" / dataset / f"date={date}" / f"{market}.csv"
                path = new_path if new_path.exists() else old_path
                if not _is_file_valid(path, min_bytes, min_lines):
                    missing.append(str(path))

    _append_missing(missing, date_list, market_type)
    return missing


if __name__ == "__main__":
    import sys

    output_dir = os.getenv("OUTPUT_DIR", "/app/data")
    market_type = os.getenv("MARKET_TYPE", "ALL").upper()
    dates = os.getenv("DATE_LIST", "")
    date_list = [d for d in dates.split(",") if d]

    if not date_list:
        print("[INFO] DATE_LIST is empty. Skip daily output check.")
        sys.exit(0)

    missing = check_daily_outputs(date_list, output_dir, market_type)
    if missing:
        print(f"[FAIL] {len(missing)} required raw file(s) missing.")
        sys.exit(1)
    sys.exit(0)
