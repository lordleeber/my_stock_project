"""
批次執行 train_eps/step4_predict_and_publish.py，涵蓋指定 playbook 日期範圍。

用法：
  venv/bin/python3 train_eps/step4_batch_predict_and_publish.py
  venv/bin/python3 train_eps/step4_batch_predict_and_publish.py --start-date 2023-08-15
  venv/bin/python3 train_eps/step4_batch_predict_and_publish.py --skip-existing
  venv/bin/python3 train_eps/step4_batch_predict_and_publish.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT_DIR = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared_config import (  # noqa: E402
    MONTH_TO_TARGET_QNUM,
    parse_playbook_date,
    playbook_release_date,
)

DEFAULT_START = "2021-08-16"
DEFAULT_END = "2025-10-11"

PKL_PATTERN = re.compile(r"^\d{14}_\d+\.\d+\.pkl$")


def all_playbook_dates(start: str, end: str) -> list[str]:
    """產生 [start, end] 區間內所有 canonical playbook 日期。"""
    start_y, start_m = parse_playbook_date(start)
    end_y, end_m = parse_playbook_date(end)
    months: list[tuple[int, int]] = []
    y, m = start_y, int(start_m)
    while (y, m) <= (end_y, int(end_m)):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return [playbook_release_date(y, f"{m:02d}") for y, m in months if f"{m:02d}" in MONTH_TO_TARGET_QNUM]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch run step4_predict_and_publish.py for a range of playbook dates."
    )
    parser.add_argument("--start-date", type=str, default=DEFAULT_START, help="YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default=DEFAULT_END, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip dates where predictions_results.csv already exists",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dates = all_playbook_dates(args.start_date, args.end_date)
    print(f"Batch predict_and_publish: {args.start_date} → {args.end_date}  ({len(dates)} dates)")

    python = sys.executable
    script = str(ROOT_DIR / "train_eps" / "step4_predict_and_publish.py")

    ok = skipped = failed = 0

    for d in dates:
        if args.skip_existing:
            out_path = ROOT_DIR / "models_eps" / d / "predictions_results.csv"
            if out_path.exists():
                print(f"[skip]  {d}  (predictions_results.csv exists)")
                skipped += 1
                continue

        input_path = ROOT_DIR / "train_eps" / "output" / d / "dataset_evaluate.csv"
        if not input_path.exists():
            print(f"[skip]  {d}  (missing train_eps/output/{d}/dataset_evaluate.csv)")
            skipped += 1
            continue

        models_dir = ROOT_DIR / "models_eps" / d
        has_model = any(PKL_PATTERN.match(p.name) for p in models_dir.glob("*.pkl"))
        if not has_model:
            print(f"[skip]  {d}  (no timestamped model pkl in models_eps/{d}/)")
            skipped += 1
            continue

        cmd = [python, script, "--date", d]

        if args.dry_run:
            print(f"[dry]   {d}  {' '.join(cmd)}")
            continue

        print(f"\n{'=' * 60}")
        print(f"[run]   {d}")
        print(f"{'=' * 60}")
        result = subprocess.run(cmd, cwd=str(ROOT_DIR))
        if result.returncode == 0:
            print(f"[ok]    {d}")
            ok += 1
        else:
            print(f"[FAIL]  {d}  (returncode={result.returncode})")
            failed += 1

    if not args.dry_run:
        print(f"\n{'=' * 60}")
        print(f"Done: ok={ok}  skipped={skipped}  failed={failed}  total={len(dates)}")


if __name__ == "__main__":
    main()
