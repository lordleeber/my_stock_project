from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run full train_eps pipeline for one market/year/month")
    parser.add_argument("--market", type=str, required=True, choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="01~12")
    parser.add_argument("--data-source", type=str, choices=["db", "api"], default="db")
    parser.add_argument("--python-exe", type=str, default=sys.executable)
    parser.add_argument("--prepare-start-year", type=int, default=None, help="optional pass-through for prepare_data.py")
    parser.add_argument("--prepare-end-year", type=int, default=None, help="optional pass-through for prepare_data.py")
    parser.add_argument("--prepare-live-year", type=int, default=None, help="optional pass-through for prepare_data.py")
    return parser.parse_args()


def normalize_month(month: str) -> str:
    m = str(month).zfill(2)
    if m < "01" or m > "12":
        raise ValueError("--month must be in 01~12")
    return m


def append_error_log(log_path: Path, step_name: str, cmd: list[str], returncode: int, stdout: str, stderr: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    lines = [
        f"[{ts}] TRAIN_EPS PIPELINE FAILED",
        f"step={step_name}",
        "cmd=" + " ".join(cmd),
        f"returncode={returncode}",
        "--- STDOUT ---",
        stdout.rstrip(),
        "--- STDERR ---",
        stderr.rstrip(),
        "=" * 80,
        "",
    ]
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_step(step_name: str, cmd: list[str], cwd: Path, log_path: Path) -> None:
    print(f"[RUN] {step_name}: {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)

    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)

    if proc.returncode != 0:
        append_error_log(log_path, step_name, cmd, proc.returncode, proc.stdout, proc.stderr)
        raise SystemExit(proc.returncode)

    print(f"[OK] {step_name}")


def main() -> None:
    args = parse_args()
    month = normalize_month(args.month)

    repo_root = Path(__file__).resolve().parent.parent
    month_dir = repo_root / "train_eps" / args.market / str(args.year) / month
    prepare_script = month_dir / "prepare_data.py"

    if not prepare_script.exists():
        raise FileNotFoundError(f"prepare_data.py not found: {prepare_script}")

    log_path = repo_root / "error_train_eps.log"
    py = args.python_exe

    prepare_cmd = [
        py,
        str(prepare_script),
        "--data-source",
        args.data_source,
    ]
    if args.prepare_start_year is not None:
        prepare_cmd.extend(["--start-year", str(args.prepare_start_year)])
    if args.prepare_end_year is not None:
        prepare_cmd.extend(["--end-year", str(args.prepare_end_year)])
    if args.prepare_live_year is not None:
        prepare_cmd.extend(["--live-year", str(args.prepare_live_year)])

    steps = [
        (
            "prepare_data",
            prepare_cmd,
        ),
        (
            "train",
            [
                py,
                str(repo_root / "train_eps" / "train.py"),
                "--market",
                args.market,
                "--year",
                str(args.year),
                "--month",
                month,
            ],
        ),
        (
            "evaluate",
            [
                py,
                str(repo_root / "train_eps" / "evaluate.py"),
                "--market",
                args.market,
                "--year",
                str(args.year),
                "--month",
                month,
            ],
        ),
        (
            "gate_and_publish",
            [
                py,
                str(repo_root / "train_eps" / "gate_and_publish.py"),
                "--market",
                args.market,
                "--year",
                str(args.year),
                "--month",
                month,
            ],
        ),
    ]

    for step_name, cmd in steps:
        run_step(step_name, cmd, repo_root, log_path)

    print("[DONE] train_eps pipeline completed")


if __name__ == "__main__":
    main()
