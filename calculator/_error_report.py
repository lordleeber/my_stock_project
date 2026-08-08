"""calculator 共用的錯誤回報。

6 支 `calculate_*.py` 原本各自抄一份 `abort_with_error()`（`calculate_valuation.py`
沒有這支——它的 runtime error 走 `traceback.print_exc()` + `sys.exit(1)`），內容
幾乎逐字相同，差別只有兩點——而兩點都是問題：

1. 5 份漏了「執行時間」那行（只有 `calculate_daily.py` 有）。報告是 `"w"` 覆寫的，
   沒有時間戳就看不出手上這份是哪一次跑留下的。這裡統一補上。
2. 寫檔沒有任何保護。`ERROR_LOG` 被 docker 建成目錄時（`RESTORE.md` §落差4），
   `open()` 就地拋 `IsADirectoryError`，後面的 `print(message)` 與
   `raise SystemExit(1)` 全部執行不到——程序仍以非 0 結束，資料不會被污染，但
   **真正的失敗原因一個字都不剩**，只剩一行指著寫 log 那行的 traceback。
   改走 `common.error_log.write_error_log()` 之後，寫不進去也會把整份報告印到
   stdout，訊息一定看得到。

呼叫端維持 `abort_with_error(message, exception=None)`，所以既有 call site 不用動：
各檔只要 `from _error_report import abort_with_error` 一行。log 檔名也收在這裡，
不再由 6 支各留一份 `ERROR_LOG` 常數——改掛載路徑只要動這一個地方。
"""

import os
import sys
from datetime import datetime

# calculator 在 container 裡是 WORKDIR=/app + COPY . .，`common` 由 compose 掛在
# /app/common；在 host 上直接跑則要把 repo root 補進 sys.path 才找得到。
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from common.error_log import format_exception, write_error_log  # noqa: E402

# 與 processor / importer 一致，掛在 container 的 /app 底下。舊版掛在檔案系統
# 根目錄（`/error_calculator.log`），為了那一個特例，`resolve_error_log_path()`
# 得多帶一條 `container_dir != "/"` 判斷，calculator 這邊也得到處 `lstrip("/")`。
ERROR_LOG = "error_calculator.log"


def build_report(message, exception=None):
    report = "# Calculator 錯誤報告\n\n"
    report += f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report += f"## 錯誤訊息\n\n{message}\n\n"
    if exception is not None:
        report += f"## Traceback\n\n```\n{format_exception(exception)}\n```\n"
    return report


def abort_with_error(message, exception=None):
    path = write_error_log(
        ERROR_LOG,
        build_report(message, exception),
        mode="w",
        notice=False,
    )
    # 這兩行必須在寫檔**之後也一定跑得到**——舊版把它們排在裸 open() 後面，
    # log 一壞就連錯誤訊息都印不出來。
    print(f"\n❌ {message}")
    if path is not None:
        print(f"錯誤已寫入 {path}")
    raise SystemExit(1)
