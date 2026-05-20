from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from shared_config import latest_playbook_date, parse_playbook_date  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full train_eps pipeline for one playbook release date"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Playbook release date YYYY-MM-DD (must be canonical: 5/8/11 月為 16 號，其餘月份為 11 號; cutoff +1). "
        "省略則自動取今天當下最新的 canonical 日。",
    )
    return parser.parse_args()


def append_error_log(
    log_path: Path,
    step_name: str,
    cmd: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
) -> None:
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
        print(
            proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr
        )

    if proc.returncode != 0:
        append_error_log(
            log_path, step_name, cmd, proc.returncode, proc.stdout, proc.stderr
        )
        raise SystemExit(proc.returncode)

    print(f"[OK] {step_name}")


def resolve_python_executable(repo_root: Path) -> str:
    preferred = [
        repo_root / ".venv" / "bin" / "python",
        repo_root / "venv" / "bin" / "python",
    ]
    for candidate in preferred:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def main() -> None:
    args = parse_args()
    if args.date is None:
        args.date = latest_playbook_date()
        print(f"[auto] --date 未指定，使用最新 canonical playbook date: {args.date}")
    parse_playbook_date(args.date)  # validate format + canonical day

    repo_root = Path(__file__).resolve().parent.parent
    prepare_script = repo_root / "train_eps" / "step1_prepare_data.py"
    if not prepare_script.exists():
        raise FileNotFoundError(
            f"shared step1_prepare_data.py not found: {prepare_script}"
        )

    log_path = repo_root / "error_train_eps.log"
    py = resolve_python_executable(repo_root)

    steps = [
        (
            "prepare_data",
            [py, str(prepare_script), "--date", args.date],
        ),
        (
            "train",
            [py, str(repo_root / "train_eps" / "step2_train.py"), "--date", args.date],
        ),
        (
            "evaluate",
            [py, str(repo_root / "train_eps" / "step3_evaluate.py"), "--date", args.date],
        ),
        (
            "predict_and_publish",
            [
                py,
                str(repo_root / "train_eps" / "step4_predict_and_publish.py"),
                "--date",
                args.date,
            ],
        ),
    ]

    for step_name, cmd in steps:
        run_step(step_name, cmd, repo_root, log_path)

    print("[DONE] train_eps pipeline completed")


if __name__ == "__main__":
    main()
