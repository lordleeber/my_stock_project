from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch run backtester/run.py month by month.")
    parser.add_argument("--start_year", type=int, required=True)
    parser.add_argument("--start_month", type=int, required=True, help="1~12")
    parser.add_argument("--end_year", type=int, required=True)
    parser.add_argument("--end_month", type=int, required=True, help="1~12")
    parser.add_argument("--strategies-root", type=Path, default=Path("strategies/output"))
    parser.add_argument("--output-root", type=Path, default=Path("backtester/output"))
    parser.add_argument("--max-calendar-buffer-days", type=int, default=60)
    parser.add_argument("--commission-rate", type=float, default=0.001425)
    parser.add_argument("--commission-discount", type=float, default=1.0)
    parser.add_argument("--tax-rate", type=float, default=0.003)
    parser.add_argument("--entry-slippage-bps", type=float, default=0.0)
    parser.add_argument("--exit-slippage-bps", type=float, default=0.0)
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


def validate_range(start_year: int, start_month: int, end_year: int, end_month: int) -> None:
    for month in (start_month, end_month):
        if month < 1 or month > 12:
            raise ValueError("month must be in 1..12")
    if ym_to_int(start_year, start_month) > ym_to_int(end_year, end_month):
        raise ValueError("start year/month must be <= end year/month")


def resolve_input_paths(strategies_root: Path, year: int, month: int) -> tuple[Path, Path]:
    month_s = f"{month:02d}"
    base = strategies_root / f"{year:04d}" / month_s
    return base / "trade_candidates.csv", base / "results_optimize" / "best_strategy.json"


def main() -> None:
    args = parse_args()
    validate_range(args.start_year, args.start_month, args.end_year, args.end_month)

    python_exe = sys.executable
    run_script = (Path(__file__).resolve().parent / "run.py").resolve()
    strategies_root = (Path.cwd() / args.strategies_root).resolve() if not args.strategies_root.is_absolute() else args.strategies_root.resolve()
    output_root = (Path.cwd() / args.output_root).resolve() if not args.output_root.is_absolute() else args.output_root.resolve()

    done = 0
    skipped = 0
    failures = 0

    for year, month in iter_months(args.start_year, args.start_month, args.end_year, args.end_month):
        month_s = f"{month:02d}"
        cand_path, best_path = resolve_input_paths(strategies_root, year, month)
        if not cand_path.exists() or not best_path.exists():
            print(f"\n=== [{year}/{month_s}] skip ===")
            missing = []
            if not cand_path.exists():
                missing.append(str(cand_path))
            if not best_path.exists():
                missing.append(str(best_path))
            print("missing inputs:")
            for p in missing:
                print(f"  - {p}")
            skipped += 1
            continue

        cmd = [
            python_exe,
            str(run_script),
            "--year",
            str(year),
            "--month",
            month_s,
            "--strategies-root",
            str(strategies_root),
            "--output-root",
            str(output_root),
            "--max-calendar-buffer-days",
            str(args.max_calendar_buffer_days),
            "--commission-rate",
            str(args.commission_rate),
            "--commission-discount",
            str(args.commission_discount),
            "--tax-rate",
            str(args.tax_rate),
            "--entry-slippage-bps",
            str(args.entry_slippage_bps),
            "--exit-slippage-bps",
            str(args.exit_slippage_bps),
        ]

        print(f"\n=== [{year}/{month_s}] run ===")
        print("Command:", " ".join(cmd))
        result = subprocess.run(cmd)
        if result.returncode == 0:
            done += 1
        else:
            failures += 1
            print(f"failed: {year}/{month_s} (code={result.returncode})")

    print("\nbatch_run completed")
    print(f"- done: {done}")
    print(f"- skipped_missing_input: {skipped}")
    print(f"- failures: {failures}")
    if failures > 0:
        raise RuntimeError(f"batch_run has {failures} failed month(s)")


if __name__ == "__main__":
    main()
