"""error log 寫入的 fail-soft 契約測試。

pytest 相容，但專案沒裝 pytest、CI 也只跑 ruff，所以本檔可直接執行：

    venv/bin/python3 common/tests/test_error_log.py

這裡測的是**錯誤處理器自己壞掉**的情境（RESTORE.md §落差4：bind mount 的 source
不存在時 docker 會把 log 建成 root 目錄）。這種 bug 特別惡毒——它只在「真的出錯
的那一天」發作，而那天你正好最需要這份 log。所以重點全放在「log 壞掉時，呼叫端
原本要傳達的東西還在不在」。

所有測試都在 `_sandbox()` 裡跑：chdir 到 tmp_path，並把 `CONTAINER_DIR` 指到一個
不存在的 tmp 子目錄。**不能**改成斷言「這台機器上沒有 /app」——CI runner、dev
container，以及本 repo 每一個 image 內部的 WORKDIR 都正好是 /app，那會讓完全正確
的程式碼紅燈。
"""

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import common.error_log as error_log_mod  # noqa: E402
from common.error_log import (  # noqa: E402
    append_error_log,
    format_exception,
    resolve_error_log_path,
    write_error_log,
)


def _load(module_name, relpath):
    """依路徑載入模組。

    processor 與 calculator 各有一支 `_error_report.py`——在正式環境它們分屬不同
    container、永遠不會同時出現在 sys.path，但測試要同時碰到兩者，直接 import
    會被先進 sys.path 的那個蓋掉。
    """
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / relpath)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROCESSOR_ERR = _load("processor_error_report", "processor/_error_report.py")
CALCULATOR_ERR = _load("calculator_error_report", "calculator/_error_report.py")


@contextlib.contextmanager
def _cwd(path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


@contextlib.contextmanager
def _sandbox(tmp_path):
    """把「container 掛載點」與 CWD 都關進 tmp_path，測試才不看宿主機臉色。"""
    prev = error_log_mod.CONTAINER_DIR
    error_log_mod.CONTAINER_DIR = str(tmp_path / "no_such_container_mount")
    try:
        with _cwd(tmp_path):
            yield
    finally:
        error_log_mod.CONTAINER_DIR = prev


def test_normal_write_and_append(tmp_path):
    with _sandbox(tmp_path):
        assert write_error_log("e.log", "one\n", notice=False) == Path("e.log")
        assert write_error_log("e.log", "two\n", mode="a", notice=False)
        assert (tmp_path / "e.log").read_text() == "one\ntwo\n"
        # mode="w" 覆寫（importer/calculator 的 abort 報告靠這個語意）
        write_error_log("e.log", "three\n", mode="w", notice=False)
        assert (tmp_path / "e.log").read_text() == "three\n"


def test_directory_target_returns_none_and_dumps_to_stdout(tmp_path):
    """log 被建成目錄時：不拋例外、回 None，而且內容要印出來——不能無聲消失。"""
    (tmp_path / "e.log").mkdir()
    buf = io.StringIO()
    with _sandbox(tmp_path), contextlib.redirect_stdout(buf):
        result = write_error_log("e.log", "THE ACTUAL ERROR\n", notice=False)
    out = buf.getvalue()
    assert result is None
    assert "THE ACTUAL ERROR" in out, "內容必須落到 stdout"
    assert "是目錄" in out, "要告訴操作者這是 bind mount 建出來的目錄"
    assert "rmdir" in out, "要給出可執行的修法"


def test_non_oserror_write_failure_is_also_swallowed(tmp_path):
    """契約是「記不下來就大聲印出來」，不是「OSError 記不下來才印出來」。

    只攔 OSError 等於留了一條例外仍會穿過去的路（例如呼叫端傳進非字串），
    呼叫端的判斷結果一樣會被吃掉——正是這個模組要根治的失敗模式。
    """
    buf = io.StringIO()
    with _sandbox(tmp_path), contextlib.redirect_stdout(buf):
        result = write_error_log("e.log", 12345, notice=False)  # 不是 str → TypeError
    assert result is None
    assert "12345" in buf.getvalue(), "內容必須落到 stdout"


def test_resolve_prefers_container_mount_then_falls_back_to_cwd(tmp_path):
    container = tmp_path / "container_root"
    container.mkdir()
    mounted = container / "error_processor.log"
    mounted.touch()

    # 有 bind mount → 就寫那個檔
    assert resolve_error_log_path("error_processor.log", str(container)) == mounted
    # mount 缺席但 container 目錄在 → 仍落在各模組文件宣告的那條路徑，不隨 CWD 漂移
    assert resolve_error_log_path("error_importer.log", str(container)) == (
        container / "error_importer.log"
    )
    # 連 container 目錄都不存在（= 在 host 上跑）→ 落回 CWD
    with _cwd(tmp_path):
        assert resolve_error_log_path(
            "error_processor.log", str(tmp_path / "nope")
        ) == Path("error_processor.log")


def test_absolute_filename_is_used_as_is(tmp_path):
    """train_eps 在 host 上跑，直接傳 repo root 的絕對路徑。"""
    target = tmp_path / "error_train_eps.log"
    assert write_error_log(str(target), "boom\n", notice=False) == target
    assert target.read_text() == "boom\n"


def test_append_error_log_format(tmp_path):
    with _sandbox(tmp_path):
        append_error_log("e.log", "some title", ["a", "b"])
        text = (tmp_path / "e.log").read_text()
    assert "] some title\n" in text
    assert text.endswith("a\nb\n")


def test_append_error_log_stringifies_non_str_lines(tmp_path):
    """舊版是 `f.write(f"{line}\\n")`，本來就吃得下 Path/int；改成 join 之後
    若不轉字串，scraper 的 checker 只要塞了非字串就會拋 TypeError。"""
    with _sandbox(tmp_path):
        assert append_error_log("e.log", "t", [Path("a/b.csv"), 3]) is not None
        text = (tmp_path / "e.log").read_text()
    assert text.endswith("a/b.csv\n3\n")


def test_format_exception_uses_the_passed_exception(tmp_path):
    """報告要格式化**傳進來的**那個 exception。`traceback.format_exc()` 拿的是
    「目前正在處理的例外」——在 except 區塊外呼叫會拿到 "NoneType: None" 或上一個
    不相干的 traceback，報告卻長得像是它的。"""
    try:
        raise ValueError("the real one")
    except ValueError as e:
        saved = e

    # 已經離開 except 區塊，此處 sys.exc_info() 是空的
    text = format_exception(saved)
    assert "the real one" in text
    assert "ValueError" in text
    assert "NoneType: None" not in text

    report = CALCULATOR_ERR.build_report("boom", saved)
    assert "the real one" in report, "calculator 的報告也要拿到正確的 traceback"


def test_processor_parsing_error_stays_non_fatal(tmp_path):
    """log_parsing_error 的呼叫點在 except 區塊裡（記一筆→回 None→跳過該檔）。
    log 壞掉時若拋例外，就把一個可復原的解析錯誤升級成整個 run 中斷。"""
    (tmp_path / "error_processor.log").mkdir()
    buf = io.StringIO()
    with _sandbox(tmp_path), contextlib.redirect_stdout(buf):
        PROCESSOR_ERR.log_parsing_error(
            "data/raw/x/20260807/sii.csv", "Failed to parse CSV: boom"
        )
    assert "Failed to parse CSV: boom" in buf.getvalue()


def test_processor_audit_error_still_lets_the_typed_exception_through(tmp_path):
    """write_error_report 之後呼叫端才 raise DataQualityError。這裡若先炸掉，
    6 處 except DataQualityError 的分類處理全部落空。"""
    (tmp_path / "error_processor.log").mkdir()
    buf = io.StringIO()
    with _sandbox(tmp_path), contextlib.redirect_stdout(buf):
        PROCESSOR_ERR.write_error_report("2026-08-07", "daily_quotes", "boom")
    out = buf.getvalue()
    assert "boom" in out
    assert "Report written to" not in out, "寫不進去就不能宣稱寫進去了"


def test_processor_runtime_error_does_not_claim_a_log_it_failed_to_write(tmp_path):
    """log_processing_error 同理：訊息一定要印，但「已寫入 log」只有真的寫進去
    才能講——否則操作者照著這句去翻一個空目錄，會誤判成沒發生錯誤。"""
    (tmp_path / "error_processor.log").mkdir()
    buf = io.StringIO()
    with _sandbox(tmp_path), contextlib.redirect_stdout(buf):
        PROCESSOR_ERR.log_processing_error("boom", "20260807", "daily_quotes")
    out = buf.getvalue()
    assert "boom" in out
    assert "Error logged to" not in out, "寫不進去就不能宣稱寫進去了"


def test_calculator_abort_prints_the_message_then_exits_1(tmp_path):
    """舊版把 print(message) 排在裸 open() 後面，log 一壞就連錯誤訊息都印不出來，
    只剩一行指著寫 log 那行的 IsADirectoryError。"""
    (tmp_path / "error_calculator.log").mkdir()

    buf = io.StringIO()
    with _sandbox(tmp_path), contextlib.redirect_stdout(buf):
        try:
            CALCULATOR_ERR.abort_with_error("daily_quotes 2026-08-07 缺 1234 筆")
        except SystemExit as e:
            code = e.code
    out = buf.getvalue()
    assert code == 1, "仍必須以非 0 結束，資料才不會被污染"
    assert "daily_quotes 2026-08-07 缺 1234 筆" in out, "錯誤訊息不能消失"
    assert "錯誤已寫入" not in out, "寫不進去就不能宣稱寫進去了"


def test_calculator_abort_normal_path_writes_report(tmp_path):
    with _sandbox(tmp_path), contextlib.redirect_stdout(io.StringIO()):
        try:
            CALCULATOR_ERR.abort_with_error("boom")
        except SystemExit:
            pass
        text = (tmp_path / "error_calculator.log").read_text()
    assert "# Calculator 錯誤報告" in text
    assert "執行時間:" in text, "5 支 calculator 原本漏了時間戳，report 是覆寫的"
    assert "boom" in text


def _run_standalone() -> int:
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        with tempfile.TemporaryDirectory() as td:
            try:
                if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                    fn(Path(td))
                else:
                    fn()
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"ERROR {name}: {type(e).__name__}: {e}")
            else:
                print(f"ok   {name}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
