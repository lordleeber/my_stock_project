"""processor 共用的錯誤回報。

原本 `log_processing_error()` / `fail_invalid_params()` 在 `convert_daily.py`、
`daily/convert_institutional_summary.py`、`daily/convert_margin_summary.py`、
`convert_monthly.py` 各抄一份（格式相同，只有 `**Entry:**` 那行不同），加上
`audit_base.write_error_report()` 與 `utils.log_parsing_error()` 兩種格式，
一共 8 個裸 `open()`。

全部改走 `common.error_log.write_error_log()`，理由見該檔 docstring。對 processor
來說最要命的是 `log_parsing_error()`：它被呼叫的位置在 `except` 區塊裡，本來是
「記一筆、回 None、跳過這個檔」的**降級**路徑，log 一壞就變成把整個 run 打死的
未捕捉例外——嚴重度從降級直接升成中斷。`write_error_report()` 則會讓
`raise DataQualityError` 來不及執行，6 處 `except DataQualityError` 的分類處理
全部落空。

各函式的輸出格式與舊版逐字相同，只是外面包上 fail-soft。
"""

import datetime
import os
import sys
import traceback
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.error_log import write_error_log  # noqa: E402

ERROR_LOG = "error_processor.log"


def _timestamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_processing_error(msg, date_str=None, category=None):
    """處理階段的錯誤（非致命，呼叫端自行決定後續）。"""
    report = f"\n## Processor Runtime Error - {_timestamp()}\n"
    if date_str:
        report += f"**Date:** {date_str}\n"
    if category:
        report += f"**Category:** {category}\n"
    report += f"**Message:** {msg}\n"
    report += f"**Traceback:**\n```python\n{traceback.format_exc()}\n```\n"
    report += "---\n"

    path = write_error_log(ERROR_LOG, report, mode="a", notice=False)
    # 訊息本身一定要印；「已寫入 log」只有真的寫進去才能講，否則操作者會照著這句
    # 去翻一個空目錄，然後誤判成「處理器沒記到東西 = 沒發生錯誤」。
    if path is not None:
        print(f"❌ Error logged to {path}: {msg}")
    else:
        print(f"❌ Error: {msg}")


def fail_invalid_params(msg, entry=None, category=None):
    """參數驗證失敗：記一筆後直接以非 0 結束。"""
    report = f"\n## Processor Runtime Error - {_timestamp()}\n"
    if entry:
        report += f"**Entry:** {entry}\n"
    if category:
        report += f"**Category:** {category}\n"
    report += f"**Message:** {msg}\n"
    report += "---\n"

    write_error_log(ERROR_LOG, report, mode="a", notice=False)
    print(msg)
    raise SystemExit(1)


def write_error_report(date_str, category, issue):
    """audit 的資料品質錯誤。呼叫端（`_raise_error`）接著 raise DataQualityError，
    所以這裡**絕對不能**拋例外，否則那個型別化的例外永遠送不出去。"""
    report = f"\n## Data Quality Error - {date_str}\n"
    report += f"**Detected at:** {_timestamp()}\n"
    report += f"**Category:** {category}\n"
    report += f"**Error:** {issue}\n"
    report += "\n**Processing stopped. Fix this error before continuing.**\n"
    report += "---\n"

    path = write_error_log(ERROR_LOG, report, mode="a", notice=False)
    print(f"\n❌ Data quality error in {category}:")
    print(f"   {issue}")
    # 寫不進去時不要宣稱寫進去了——issue 上面已經印過，write_error_log 也會把
    # 整份報告 dump 到 stdout，不會有東西消失。
    if path is not None:
        print(f"📝 Report written to {path}")


def log_parsing_error(file_path, msg, exception=None):
    """CSV 解析階段的錯誤。這是**降級**路徑（呼叫端接著 return None 跳過該檔），
    所以寫 log 失敗絕不能升級成中斷。"""
    date_str = "Unknown"
    parts = Path(file_path).parts
    if len(parts) >= 2:
        potential_date = parts[-2]
        if len(potential_date) == 8 and potential_date.isdigit():
            date_str = potential_date

    report = f"\n## Utils Parsing Error - {_timestamp()}\n"
    report += f"**Date:** {date_str}\n"
    report += f"**File:** {Path(file_path).name}\n"
    report += f"**Message:** {msg}\n"
    if exception:
        report += f"**Exception:** {str(exception)}\n"
    report += "---\n"

    write_error_log(ERROR_LOG, report, mode="a", notice=False)
