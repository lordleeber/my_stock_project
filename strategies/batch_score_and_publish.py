"""
批次對所有有 dataset_strategy.csv 的月份進行評分。

掃描 strategies/output/ 底下所有含 dataset_strategy.csv 的年月目錄，
依序執行 score_and_publish。

用法：
  venv/bin/python3 strategies/batch_score_and_publish.py
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategies.score_and_publish import score_and_publish


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-score all months.")
    parser.add_argument(
        "--verbose", action="store_true", help="Print per-month output"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    strategies_out = ROOT_DIR / "strategies" / "output"
    if not strategies_out.exists():
        print(f"strategies/output not found: {strategies_out}")
        sys.exit(1)

    months: list[tuple[int, int]] = []
    for y_dir in sorted(strategies_out.iterdir()):
        if not y_dir.is_dir():
            continue
        try:
            year = int(y_dir.name)
        except ValueError:
            continue
        for m_dir in sorted(y_dir.iterdir()):
            if not m_dir.is_dir():
                continue
            try:
                month = int(m_dir.name)
            except ValueError:
                continue
            if (m_dir / "dataset_strategy.csv").exists():
                months.append((year, month))

    if not months:
        print("No dataset_strategy.csv files found.")
        return

    print(f"Found {len(months)} months to score: {months[0]} → {months[-1]}")

    ok = 0
    failed: list[tuple[int, int, str]] = []
    for year, month in months:
        month_s = f"{month:02d}"
        try:
            if args.verbose:
                score_and_publish(year, month)
            else:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    score_and_publish(year, month)
            ok += 1
        except Exception as exc:
            print(f"[FAIL] {year}/{month_s}: {exc}")
            failed.append((year, month, str(exc)))

    print(f"\nDone: {ok} ok, {len(failed)} failed")
    if failed:
        print("Failed months:")
        for y, m, err in failed:
            print(f"  {y}/{m:02d}: {err}")


if __name__ == "__main__":
    main()
