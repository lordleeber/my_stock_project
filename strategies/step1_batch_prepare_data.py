"""
批次執行 strategies/step1_prepare_data.py，涵蓋指定 playbook date 範圍。

用法：
  venv/bin/python3 strategies/step1_batch_prepare_data.py
  venv/bin/python3 strategies/step1_batch_prepare_data.py --start-date 2023-08-16
  venv/bin/python3 strategies/step1_batch_prepare_data.py --start-date 2021-08-16 --end-date 2025-10-11
  venv/bin/python3 strategies/step1_batch_prepare_data.py --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.shared_config import (  # noqa: E402
    MONTH_TO_TARGET_QNUM,
    parse_playbook_date,
    playbook_release_date,
)

DEFAULT_START = "2021-08-16"
DEFAULT_END = "2025-10-11"


def all_playbook_dates(start: str, end: str) -> list[str]:
    """產生 [start, end] 區間內所有 canonical playbook release dates。"""
    start_y, start_m = parse_playbook_date(start)
    end_y, end_m = parse_playbook_date(end)
    out: list[str] = []
    y, m = start_y, int(start_m)
    while (y, m) <= (end_y, int(end_m)):
        mm = f"{m:02d}"
        if mm in MONTH_TO_TARGET_QNUM:
            out.append(playbook_release_date(y, mm))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run step1_prepare_data.py for a range of playbook dates."
    )
    parser.add_argument(
        "--start-date", type=str, default=DEFAULT_START, help="YYYY-MM-DD"
    )
    parser.add_argument("--end-date", type=str, default=DEFAULT_END, help="YYYY-MM-DD")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip dates where dataset_strategy.csv already exists",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-date output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dates = all_playbook_dates(args.start_date, args.end_date)
    print(
        f"Batch step1_prepare_data: {args.start_date} → {args.end_date}  ({len(dates)} dates)"
    )

    python = sys.executable
    script = str(ROOT_DIR / "strategies" / "step1_prepare_data.py")

    ok = skipped = failed = 0

    for d in dates:
        if args.skip_existing:
            out_path = ROOT_DIR / "strategies" / "output" / d / "dataset_strategy.csv"
            if out_path.exists():
                if args.verbose:
                    print(f"[skip]  {d}  (dataset_strategy.csv exists)")
                skipped += 1
                continue

        cmd = [python, script, "--date", d]

        if args.dry_run:
            print(f"[dry]   {d}  {' '.join(cmd)}")
            continue

        if args.verbose:
            print(f"\n{'=' * 60}")
            print(f"[run]   {d}")
            print(f"{'=' * 60}")
        result = subprocess.run(
            cmd,
            cwd=str(ROOT_DIR),
            stdout=None if args.verbose else subprocess.DEVNULL,
            stderr=None if args.verbose else subprocess.DEVNULL,
        )
        if result.returncode == 0:
            if args.verbose:
                print(f"[ok]    {d}")
            ok += 1
        else:
            print(f"[FAIL]  {d}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(
            f"\nDone: ok={ok}  skipped={skipped}  failed={failed}  total={len(dates)}"
        )


if __name__ == "__main__":
    main()
