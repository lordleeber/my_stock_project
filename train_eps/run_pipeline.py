from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for _path in (_HERE, _HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from common.error_log import write_error_log  # noqa: E402
from shared_config import latest_playbook_date, parse_playbook_date  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full train_eps pipeline for one playbook run date"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Playbook release date YYYY-MM-DD (must be canonical: 5/8/11 月為 16 號，其餘月份為 11 號; cutoff +1). "
        "省略則自動取今天當下最新的 canonical 日。",
    )
    return parser.parse_args()


def log_step_failure(
    log_path: Path,
    step_name: str,
    cmd: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
) -> None:
    """把失敗的 step 記進 `error_train_eps.log`（格式與舊版逐字相同）。

    寫入走 `common.error_log`（**fail-soft**）：舊版是裸 `log_path.open("a")`，
    log 一旦被建成目錄就在這一行拋 `IsADirectoryError`，連帶把 step 的
    returncode / stdout / stderr 全部吃掉，而 `raise SystemExit(returncode)`
    也執行不到——正是 `RESTORE.md` §落差4 那個失敗模式。現在寫不進去會把整筆
    內容 dump 到 stdout，退出碼一定送得出去。
    """
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
    write_error_log(str(log_path), "\n".join(lines), mode="a", notice=False)


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
        log_step_failure(
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
            [
                py,
                str(repo_root / "train_eps" / "step3_evaluate.py"),
                "--date",
                args.date,
            ],
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
