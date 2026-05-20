"""
批次對所有有 dataset_strategy.csv 的 playbook date 進行評分。

掃描 strategies/output/<YYYY-MM-DD>/dataset_strategy.csv 的目錄，
依序執行 step5_score_and_publish。

用法：
  venv/bin/python3 strategies/step5_batch_score_and_publish.py
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

from strategies.shared_config import parse_playbook_date  # noqa: E402
from strategies.step5_score_and_publish import score_and_publish  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-score all playbook dates.")
    parser.add_argument("--verbose", action="store_true", help="Print per-date output")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    strategies_out = ROOT_DIR / "strategies" / "output"
    if not strategies_out.exists():
        print(f"strategies/output not found: {strategies_out}")
        sys.exit(1)

    dates: list[str] = []
    for d in sorted(strategies_out.iterdir()):
        if not d.is_dir():
            continue
        try:
            parse_playbook_date(d.name)
        except ValueError:
            continue
        if (d / "dataset_strategy.csv").exists():
            dates.append(d.name)

    if not dates:
        print("No dataset_strategy.csv files found.")
        return

    print(f"Found {len(dates)} dates to score: {dates[0]} → {dates[-1]}")

    ok = 0
    failed: list[tuple[str, str]] = []
    for d in dates:
        try:
            if args.verbose:
                score_and_publish(d)
            else:
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    score_and_publish(d)
            ok += 1
        except Exception as exc:
            print(f"[FAIL] {d}: {exc}")
            failed.append((d, str(exc)))

    print(f"\nDone: {ok} ok, {len(failed)} failed")
    if failed:
        print("Failed dates:")
        for d, err in failed:
            print(f"  {d}: {err}")


if __name__ == "__main__":
    main()
