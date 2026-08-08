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
import traceback
from pathlib import Path

CONTAINER_DIR = "/app"


def resolve_error_log_path(filename: str, container_dir: str | None = None) -> Path:
    """容器內走 `<container_dir>/<filename>`（compose 有 bind mount 出來），
    容器外（測試、手動執行）落回 CWD。

    `container_dir` 預設在**呼叫時**才讀模組層的 `CONTAINER_DIR`（不是綁在函式
    簽名的預設值上），這樣測試可以把它指到 tmp 目錄，不必依賴「執行測試的機器上
    剛好沒有 /app」——CI runner 與本 repo 每個 image 內部的 WORKDIR 都正好是 /app。

    先看「這個路徑存不存在」：有 bind mount 時檔案（或那個誤建的目錄）一定存在，
    所以這個訊號最可靠；mount 缺席時退而求其次看 parent 在不在，讓 container 內
    仍寫到各模組文件宣告的那條路徑，而不是隨 CWD 漂移。

    `filename` 給絕對路徑時兩者都會直接沿用它（`Path("/app") / "/x/y"` 就是
    `Path("/x/y")`）——host 端的呼叫者（train_eps）靠這個直接傳完整路徑。
    """
    candidate = (
        Path(CONTAINER_DIR if container_dir is None else container_dir) / filename
    )
    # 目錄的情況也回傳它，好讓 _dump_to_stdout 的警告指名正確的路徑。
    if candidate.exists() or candidate.parent.is_dir():
        return candidate
    return Path(filename)


def format_exception(exception) -> str:
    """格式化**傳進來的**那個 exception（給各模組的錯誤報告用）。

    不能用 `traceback.format_exc()`——那拿的是「目前正在處理的例外」。呼叫端只要
    不是在 `except` 區塊裡寫報告（先把 e 存起來、或在 finally／回呼裡才寫），
    `format_exc()` 就會回 `"NoneType: None"` 或上一個不相干的 traceback，而報告
    看起來卻像是這個 exception 的。
    """
    return "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )


def _dump_to_stdout(target, text, error):
    """寫不進 log 時的最後手段：整筆內容改印到 stdout。

    這個函式自己也必須 fail-soft——它是「錯誤處理器壞掉」時唯一還在跑的東西，
    連它都拋例外（stdout 已關閉、編碼吃不下這段文字…）就又回到本模組要根治的
    那個 bug：呼叫端的判斷結果被寫 log 的失敗吃掉。
    """
    try:
        print(f"\n[WARN] Cannot write {target}: {error}")
        if isinstance(target, Path) and target.is_dir():
            print(
                f"[WARN] {target} 是目錄，不是檔案——bind mount 的 source 不存在時 "
                "docker 會這樣建。修法：停掉 container 後 `sudo rmdir` 它，"
                f"再 `touch {target.name}`（見 RESTORE.md §2，或跑 "
                "schedules/ensure_error_logs.sh）。"
            )
        print("[WARN] Dumping the record to stdout instead:")
        print(text)
    except Exception:
        # 連 stdout 都沒了就真的無計可施。吞掉——絕不能讓「印不出來」本身
        # 變成往呼叫端拋的例外。
        pass


def write_error_log(
    filename: str,
    text: str,
    *,
    mode: str = "a",
    container_dir: str | None = None,
    notice: bool = True,
):
    """把 `text` 原樣寫進 error log，回傳實際寫入的路徑；寫不進去時回傳 None。

    寫入失敗**不會**拋例外——呼叫端一律應該依自己的判斷結果決定退出碼，
    而不是依這裡有沒有成功。`mode` 沿用各呼叫端原本的語意（"a" 追加、"w" 覆寫）。
    """
    path = None
    try:
        path = resolve_error_log_path(filename, container_dir)
        with path.open(mode, encoding="utf-8") as f:
            f.write(text)
    except Exception as e:
        # 刻意攔 Exception 而不是 OSError：這層的**唯一**職責就是不讓寫 log 的
        # 失敗蓋掉呼叫端的判斷結果，所以連 TypeError / UnicodeEncodeError 這種
        # 「呼叫端傳了奇怪東西」的錯也一併吸收。只放行 OSError 等於留了一條
        # 例外仍會穿過去的路，那正是這個模組要根治的失敗模式。
        _dump_to_stdout(path if path is not None else filename, text, e)
        return None

    if notice:
        print(f"\n[WARN] Issues detected. See: {path}")
    return path


def append_error_log(
    filename: str, title: str, lines, container_dir: str | None = None
):
    """scraper 各 checker 用的格式：`[timestamp] title` 後面接一串明細行。

    `lines` 逐項 `str()`：舊版是 `f.write(f"{line}\\n")`，本來就吃得下 Path/int，
    改成 join 之後若不轉字串會變成 TypeError。
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    detail = [str(line) for line in lines]
    record = "\n".join([f"\n[{timestamp}] {title}"] + detail) + "\n"
    return write_error_log(filename, record, mode="a", container_dir=container_dir)
