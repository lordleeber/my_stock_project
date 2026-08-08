import sys
from pathlib import Path

# Backward-compatible wrapper:
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from weekly.check_outputs import main


if __name__ == "__main__":
    # 必須把 main() 的回傳值轉成 exit code：weekly/check_outputs.py 的 gate 靠
    # 非零退出才擋得住 weekly_update.sh 的 set -e。裸呼叫 main() 會永遠 exit 0，
    # 也就是這道 gate 本來要消滅的「靜默通過」。
    raise SystemExit(main())
