import subprocess
from pathlib import Path


RANGES = [
    (2022, 8, 2022, 12),
    (2023, 1, 2023, 12),
    (2024, 1, 2024, 12),
    (2025, 1, 2025, 10),
]


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    python_exe = repo_root / "venv" / "bin" / "python"
    summarize_script = repo_root / "backtester" / "summarize_range.py"

    if not python_exe.exists():
        raise FileNotFoundError(f"python executable not found: {python_exe}")
    if not summarize_script.exists():
        raise FileNotFoundError(f"summarize script not found: {summarize_script}")

    for start_year, start_month, end_year, end_month in RANGES:
        cmd = [
            str(python_exe),
            str(summarize_script),
            "--start_year",
            str(start_year),
            "--start_month",
            str(start_month),
            "--end_year",
            str(end_year),
            "--end_month",
            str(end_month),
        ]
        print(f"\n=== summarize_range {start_year}-{start_month:02d} ~ {end_year}-{end_month:02d} ===")
        print("Command:", " ".join(cmd))
        subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
