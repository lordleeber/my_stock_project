#!/usr/bin/env python3
import argparse
import os
from pathlib import Path


RAW_DIR = Path("data/raw")

DATASETS = [
    "daily_quotes",
    "institutional_summary",
    "institutional_investors",
    "foreign_holding",
    "margin_trading",
    "margin_sbl",
    "pe_ratio",
]

MARKETS = ["sii", "otc"]


def file_ok(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def get_path(dataset, date, market):
    new_path = RAW_DIR / dataset / date[:4] / date / f"{market}.csv"
    if new_path.exists():
        return new_path
    return RAW_DIR / dataset / f"date={date}" / f"{market}.csv"


def main():
    parser = argparse.ArgumentParser(
        description="Check scraper-daily outputs for a given date."
    )
    parser.add_argument("--date", required=True, help="YYYYMMDD")
    parser.add_argument(
        "--markets",
        default="sii,otc",
        help="Comma-separated markets to check (default: sii,otc)",
    )
    parser.add_argument(
        "--datasets",
        default=",".join(DATASETS),
        help=f"Comma-separated datasets to check (default: {','.join(DATASETS)})",
    )
    args = parser.parse_args()

    date = args.date.strip()
    markets = [m.strip() for m in args.markets.split(",") if m.strip()]
    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]

    missing = []
    for dataset in datasets:
        for market in markets:
            path = get_path(dataset, date, market)
            if not file_ok(path):
                missing.append(str(path))

    # Heuristic: if both daily_quotes files are missing, likely non-trading day
    dq_missing = all(
        not file_ok(get_path("daily_quotes", date, m))
        for m in markets
        if m in MARKETS
    )

    if missing:
        if dq_missing:
            print(f"{date}: daily_quotes missing for all markets; likely non-trading day.")
        print("Missing files:")
        for path in missing:
            print(path)
        raise SystemExit(1)

    print(f"{date}: all expected files present.")


if __name__ == "__main__":
    main()
