import sys
from pathlib import Path

# Backward-compatible wrapper:
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from weekly.check_outputs import main


if __name__ == "__main__":
    main()
