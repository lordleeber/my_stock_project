import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Automation pipeline for strategy workflow.")
    parser.add_argument("--market", type=str, required=True, choices=["sii", "otc"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=str, required=True, help="e.g. 08")
    return parser.parse_args()


def log_error(message: str):
    root_dir = Path(__file__).resolve().parent.parent
    log_path = root_dir / "error_strategies.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def run_command(command_list, step_name):
    print(f"--- Running {step_name} ---")
    print(f"Command: {' '.join(command_list)}")
    
    # 使用當前環境的 Python (也就是 .venv 中的 python)
    result = subprocess.run(command_list, capture_output=True, text=True)
    
    if result.returncode != 0:
        error_msg = f"Step '{step_name}' failed with return code {result.returncode}.\n"
        error_msg += f"STDOUT: {result.stdout}\n"
        error_msg += f"STDERR: {result.stderr}\n"
        print(error_msg)
        log_error(error_msg)
        return False
    
    print(f"Step '{step_name}' completed successfully.\n")
    return True


def main():
    args = parse_args()
    market = args.market
    year = str(args.year)
    month = str(args.month).zfill(2)

    # 取得當前執行此腳本的 Python 路徑 (.venv/Scripts/python.exe)
    python_exe = sys.executable

    print(f"\n{'='*60}")
    print(f"Strategy Pipeline: {market.upper()} {year}/{month}")
    print(f"{'='*60}")
    print("Pipeline flow (look-ahead bias free):")
    print("  Step 1: Predict EPS using published model")
    print("  Step 2: Build candidates + fetch per-stock revenue publish dates")
    print("  Step 3: Cache quotes for current month AND historical periods")
    print("          (last-year same month + last month)")
    print("  Step 4: Optimize params on HISTORICAL data; apply to current month")
    print(f"{'='*60}\n")

    steps = [
        {
            "name": "Step 1 — Predict Published EPS",
            "cmd": [python_exe, "strategies/predict_published.py",
                    "--market", market, "--year", year, "--month", month],
        },
        {
            "name": "Step 2 — Build Candidates (with revenue_publish_date)",
            "cmd": [python_exe, "strategies/build_candidates.py",
                    "--market", market, "--year", year, "--month", month],
        },
        {
            "name": "Step 3 — Cache Daily Quotes (current + historical)",
            "cmd": [python_exe, "strategies/cache_daily_quotes.py",
                    "--market", market, "--year", year, "--month", month],
        },
        {
            "name": "Step 4 — Optimize Strategy (train on history, apply to current)",
            "cmd": [python_exe, "strategies/optimize_strategy.py",
                    "--market", market, "--year", year, "--month", month],
        },
    ]

    for step in steps:
        success = run_command(step["cmd"], step["name"])
        if not success:
            print(f"Pipeline aborted at step: {step['name']}")
            sys.exit(1)

    print("All strategy pipeline steps completed successfully!")


if __name__ == "__main__":
    main()
