"""error_*.log 的路徑解析與寫入（scraper 各 checker 共用）。

**為什麼寫入必須 fail-soft**：`docker-compose.yml` 用 bind mount 把這些 log 掛進
container，而 bind mount 的 source 不存在時，docker 會照 target 自動建一個
**root 所有的目錄**——之後每一次 `open(path, "a")` 都固定拋 `IsADirectoryError`。

2026-08-01 真的踩過（見 `RESTORE.md` §落差4）：`error_processor.log` 等三個檔案
被建成目錄，而壞掉的偏偏是**錯誤處理器本身**，所以「偵測到問題」的那條路徑反而
變成 traceback，呼叫端原本要回報的結果直接被跳過。對 scraper 的 weekly gate 來說
更致命：全新 clone 上第一次執行就會這樣，等於 gate 天生失效。

所以這裡的契約是：**記不下來就大聲印到 stdout，絕不讓 log 寫入的失敗吃掉呼叫端
的判斷結果。** 路徑解析同理——容器外（測試、手動執行）沒有 `/app` 時落回 CWD，
不因為 `/app` 不存在就 FileNotFoundError。
"""

import datetime
from pathlib import Path

CONTAINER_DIR = "/app"


def resolve_error_log_path(filename: str, container_dir: str = CONTAINER_DIR) -> Path:
    """容器內走 `<container_dir>/<filename>`（compose 有 bind mount 出來），
    容器外落在 CWD。"""
    app_log = Path(container_dir) / filename
    return app_log if app_log.parent.is_dir() else Path(filename)


def append_error_log(
    filename: str, title: str, lines, container_dir: str = CONTAINER_DIR
):
    """把一則錯誤紀錄追加到 error log，回傳實際寫入的路徑；寫不進去時回傳 None。

    寫入失敗**不會**拋例外——呼叫端一律應該依自己的判斷結果決定退出碼，
    而不是依這裡有沒有成功。
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = [f"\n[{timestamp}] {title}"] + list(lines)
    path = resolve_error_log_path(filename, container_dir)

    try:
        with path.open("a", encoding="utf-8") as f:
            for line in record:
                f.write(f"{line}\n")
    except OSError as e:
        print(f"\n[WARN] Cannot write {path}: {e}")
        if path.is_dir():
            print(
                f"[WARN] {path} 是目錄，不是檔案——bind mount 的 source 不存在時 "
                "docker 會這樣建。修法：停掉 container 後 `sudo rmdir` 它，"
                f"再 `touch {filename}`（見 RESTORE.md §2）。"
            )
        print("[WARN] Dumping the record to stdout instead:")
        for line in record:
            print(line)
        return None

    print(f"\n[WARN] Issues detected. See: {path}")
    return path
