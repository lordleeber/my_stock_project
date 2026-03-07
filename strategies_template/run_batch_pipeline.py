from __future__ import annotations

import subprocess
import sys


def run(cmd: list[str]) -> None:
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    commands = [
        [
            "venv/bin/python",
            "strategies/batch_prepare_data.py",
            "--start_year",
            "2021",
            "--start_month",
            "8",
            "--end_year",
            "2025",
            "--end_month",
            "10",
        ],
        [
            "venv/bin/python",
            "strategies/batch_predict_published.py",
            "--start_year",
            "2021",
            "--start_month",
            "8",
            "--end_year",
            "2025",
            "--end_month",
            "10",
        ],
        [
            "venv/bin/python",
            "strategies/batch_build_candidates.py",
            "--start_year",
            "2021",
            "--start_month",
            "8",
            "--end_year",
            "2025",
            "--end_month",
            "10",
        ],
        [
            "venv/bin/python",
            "strategies/batch_cache_daily_quotes.py",
            "--start_year",
            "2022",
            "--start_month",
            "8",
            "--end_year",
            "2025",
            "--end_month",
            "10",
        ],
        [
            "venv/bin/python",
            "strategies/batch_optimize_strategy.py",
            "--start_year",
            "2022",
            "--start_month",
            "8",
            "--end_year",
            "2025",
            "--end_month",
            "10",
        ],
    ]

    for cmd in commands:
        run(cmd)
