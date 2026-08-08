"""error_*.log 的路徑解析與寫入（scraper / processor / importer / calculator 共用）。

**為什麼寫入必須 fail-soft**：`docker-compose.yml` 用 **file** bind mount 把這些 log
掛進 container，而 bind mount 的 source 不存在時，docker 會照 target 自動建一個
**root 所有的目錄**——之後每一次 `open(path, ...)` 都固定拋 `IsADirectoryError`。

2026-08-01 真的踩過（見 `RESTORE.md` §落差4）：`error_processor.log` 等三個檔案
被建成目錄，而壞掉的偏偏是**錯誤處理器本身**。三種後果各不相同：

- `abort_with_error()`（importer / calculator）：例外在寫檔那行就拋出，後面的
  `print(message)` 與 `raise SystemExit(1)` 都執行不到。程序仍以非 0 結束（資料
  不會被污染），但**真正的失敗原因一個字都不剩**，log 裡只有一行指著寫 log 那
  行的 `IsADirectoryError`。
- `write_error_report()`（processor/audit_base）：`DataQualityError` 來不及 raise，
  6 處 `except DataQualityError` 的分類處理全部落空。
- `log_parsing_error()`（processor/utils）：它被呼叫的位置在 `except` 區塊裡，
  本來是「記一筆、回 None、跳過這個檔」的**降級**路徑，log 一壞就變成把整個
  processor run 打死的未捕捉例外——嚴重度直接從降級升成中斷。

所以這裡的契約是：**記不下來就大聲印到 stdout，絕不讓 log 寫入的失敗吃掉呼叫端
的判斷結果。** 各模組原本的 log 格式一律保留，只是外面包上這層保險。
"""

import datetime
from pathlib import Path

CONTAINER_DIR = "/app"


def resolve_error_log_path(filename: str, container_dir: str = CONTAINER_DIR) -> Path:
    """容器內走 `<container_dir>/<filename>`（compose 有 bind mount 出來），
    容器外（測試、手動執行）落回 CWD。

    判斷順序刻意以「這個路徑存不存在」為主，而不是只看 parent 在不在：calculator
    的 log 掛在 `/error_calculator.log`，parent 是 `/`——那在 host 上永遠存在，
    只看 parent 會讓 host 端解析到 `/error_calculator.log` 然後 permission denied。
    有 bind mount 時檔案（或那個誤建的目錄）一定存在，所以這個訊號更可靠。
    """
    candidate = Path(container_dir) / filename
    if candidate.exists():
        # 目錄的情況也回傳它，好讓 write_error_log 的警告指名正確的路徑。
        return candidate
    if container_dir != "/" and candidate.parent.is_dir():
        return candidate
    return Path(filename)


def write_error_log(
    filename: str,
    text: str,
    *,
    mode: str = "a",
    container_dir: str = CONTAINER_DIR,
    notice: bool = True,
):
    """把 `text` 原樣寫進 error log，回傳實際寫入的路徑；寫不進去時回傳 None。

    寫入失敗**不會**拋例外——呼叫端一律應該依自己的判斷結果決定退出碼，
    而不是依這裡有沒有成功。`mode` 沿用各呼叫端原本的語意（"a" 追加、"w" 覆寫）。
    """
    path = resolve_error_log_path(filename, container_dir)
    try:
        with path.open(mode, encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        print(f"\n[WARN] Cannot write {path}: {e}")
        if path.is_dir():
            print(
                f"[WARN] {path} 是目錄，不是檔案——bind mount 的 source 不存在時 "
                "docker 會這樣建。修法：停掉 container 後 `sudo rmdir` 它，"
                f"再 `touch {filename}`（見 RESTORE.md §2，或跑 "
                "schedules/ensure_error_logs.sh）。"
            )
        print("[WARN] Dumping the record to stdout instead:")
        print(text)
        return None

    if notice:
        print(f"\n[WARN] Issues detected. See: {path}")
    return path


def append_error_log(
    filename: str, title: str, lines, container_dir: str = CONTAINER_DIR
):
    """scraper 各 checker 用的格式：`[timestamp] title` 後面接一串明細行。"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = "\n".join([f"\n[{timestamp}] {title}"] + list(lines)) + "\n"
    return write_error_log(filename, record, mode="a", container_dir=container_dir)
