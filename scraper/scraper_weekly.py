import os
import sys
from pathlib import Path

# Ensure project root is importable when executed as a script.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.weekly import fetch_tdcc
from scraper.weekly.check_outputs import check_weekly_outputs


def main():
    output_dir = "/app/data/raw/shareholding"
    output_root = "/app/data"

    # Reuse existing fetch_tdcc CLI implementation with non-interactive flags.
    sys.argv = [
        "fetch_tdcc.py",
        "--no-prompt",
        "--no-verify",
        "--output-dir",
        output_dir,
    ]
    rc = fetch_tdcc.main()
    if rc != 0:
        return rc

    tdcc_date = os.getenv("TDCC_DATE", "").strip()
    missing = check_weekly_outputs(output_root, tdcc_date)
    if missing:
        # 與 scraper_daily.py 同慣例：checker 回報問題就讓 entrypoint 非零退出，
        # weekly_update.sh 的 set -e 會中斷，systemd 的 OnFailure 才推得出通知。
        print(f"[FAIL] {len(missing)} weekly output problem(s) detected.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
