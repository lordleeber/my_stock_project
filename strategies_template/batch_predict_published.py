import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch run strategies/predict_published.py by month range.")
    parser.add_argument("--start_year", type=int, required=True)
    parser.add_argument("--start_month", type=int, required=True, help="1~12")
    parser.add_argument("--end_year", type=int, required=True)
    parser.add_argument("--end_month", type=int, required=True, help="1~12")
    return parser.parse_args()


def ym_to_int(year: int, month: int) -> int:
    return year * 12 + month


def iter_months(start_year: int, start_month: int, end_year: int, end_month: int):
    y, m = start_year, start_month
    while (y < end_year) or (y == end_year and m <= end_month):
        yield y, m
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1


def main() -> None:
    args = parse_args()
    for m in (args.start_month, args.end_month):
        if m < 1 or m > 12:
            raise ValueError("month must be in 1..12")
    if ym_to_int(args.start_year, args.start_month) > ym_to_int(args.end_year, args.end_month):
        raise ValueError("start year/month must be <= end year/month")

    predict_script = (Path(__file__).resolve().parent / "predict_published.py").resolve()
    python_exe = sys.executable

    total = 0
    for year, month in iter_months(args.start_year, args.start_month, args.end_year, args.end_month):
        month_s = f"{month:02d}"
        cmd = [
            python_exe,
            str(predict_script),
            "--year",
            str(year),
            "--month",
            month_s,
        ]
        print(f"\n=== [{year}/{month_s}] predict_published ===")
        print("Command:", " ".join(cmd))
        result = subprocess.run(cmd)
        if result.returncode != 0:
            raise RuntimeError(f"predict_published failed at {year}/{month_s} (code={result.returncode})")
        total += 1

    print(f"\nbatch_predict_published done: {total} month(s)")


if __name__ == "__main__":
    main()
