"""error log 寫入的 fail-soft 契約測試。

pytest 相容，但專案沒裝 pytest、CI 也只跑 ruff，所以本檔可直接執行：

    venv/bin/python3 common/tests/test_error_log.py

這裡測的是**錯誤處理器自己壞掉**的情境（RESTORE.md §落差4：bind mount 的 source
不存在時 docker 會把 log 建成 root 目錄）。這種 bug 特別惡毒——它只在「真的出錯
的那一天」發作，而那天你正好最需要這份 log。所以重點全放在「log 壞掉時，呼叫端
原本要傳達的東西還在不在」。
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

from common.error_log import (  # noqa: E402
    append_error_log,
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


def test_normal_write_and_append(tmp_path):
    with _cwd(tmp_path):
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
    with _cwd(tmp_path), contextlib.redirect_stdout(buf):
        result = write_error_log("e.log", "THE ACTUAL ERROR\n", notice=False)
    out = buf.getvalue()
    assert result is None
    assert "THE ACTUAL ERROR" in out, "內容必須落到 stdout"
    assert "是目錄" in out, "要告訴操作者這是 bind mount 建出來的目錄"
    assert "rmdir" in out, "要給出可執行的修法"


def test_host_does_not_resolve_to_container_paths(tmp_path):
    """容器外要落回 CWD。calculator 的 log 掛在 `/`，若只看 parent 存不存在，
    host 端會解析到 /error_calculator.log 然後 permission denied。"""
    with _cwd(tmp_path):
        assert resolve_error_log_path("error_processor.log") == Path(
            "error_processor.log"
        )
        assert resolve_error_log_path("error_calculator.log", "/") == Path(
            "error_calculator.log"
        )


def test_append_error_log_format(tmp_path):
    with _cwd(tmp_path):
        append_error_log("e.log", "some title", ["a", "b"])
        text = (tmp_path / "e.log").read_text()
    assert "] some title\n" in text
    assert text.endswith("a\nb\n")


def test_processor_parsing_error_stays_non_fatal(tmp_path):
    """log_parsing_error 的呼叫點在 except 區塊裡（記一筆→回 None→跳過該檔）。
    log 壞掉時若拋例外，就把一個可復原的解析錯誤升級成整個 run 中斷。"""
    (tmp_path / "error_processor.log").mkdir()
    buf = io.StringIO()
    with _cwd(tmp_path), contextlib.redirect_stdout(buf):
        PROCESSOR_ERR.log_parsing_error(
            "data/raw/x/20260807/sii.csv", "Failed to parse CSV: boom"
        )
    assert "Failed to parse CSV: boom" in buf.getvalue()


def test_processor_audit_error_still_lets_the_typed_exception_through(tmp_path):
    """write_error_report 之後呼叫端才 raise DataQualityError。這裡若先炸掉，
    6 處 except DataQualityError 的分類處理全部落空。"""
    (tmp_path / "error_processor.log").mkdir()
    buf = io.StringIO()
    with _cwd(tmp_path), contextlib.redirect_stdout(buf):
        PROCESSOR_ERR.write_error_report("2026-08-07", "daily_quotes", "boom")
    assert "boom" in buf.getvalue()


def test_calculator_abort_prints_the_message_then_exits_1(tmp_path):
    """舊版把 print(message) 排在裸 open() 後面，log 一壞就連錯誤訊息都印不出來，
    只剩一行指著寫 log 那行的 IsADirectoryError。"""
    (tmp_path / "error_calculator.log").mkdir()
    abort = CALCULATOR_ERR.make_abort("/error_calculator.log")

    buf = io.StringIO()
    with _cwd(tmp_path), contextlib.redirect_stdout(buf):
        try:
            abort("daily_quotes 2026-08-07 缺 1234 筆")
        except SystemExit as e:
            code = e.code
    assert code == 1, "仍必須以非 0 結束，資料才不會被污染"
    assert "daily_quotes 2026-08-07 缺 1234 筆" in buf.getvalue(), "錯誤訊息不能消失"


def test_calculator_abort_normal_path_writes_report(tmp_path):
    abort = CALCULATOR_ERR.make_abort("/error_calculator.log")
    with _cwd(tmp_path), contextlib.redirect_stdout(io.StringIO()):
        try:
            abort("boom")
        except SystemExit:
            pass
        text = (tmp_path / "error_calculator.log").read_text()
    assert "# Calculator 錯誤報告" in text
    assert "執行時間:" in text, "6 支 calculator 原本漏了時間戳，report 是覆寫的"
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
