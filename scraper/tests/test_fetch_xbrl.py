"""fetch_xbrl 的回應驗證與失敗分類測試。

pytest 相容，但因為專案目前沒有安裝 pytest、CI 也沒跑（只跑 ruff），
本檔可以直接執行：

    venv/bin/python3 scraper/tests/test_fetch_xbrl.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "quarterly"))

from fetch_xbrl import (  # noqa: E402
    MIN_REPORT_BYTES,
    base_status,
    classify_failure_reason,
    decide_exit_code,
    is_valid_report_file,
    load_existing_report_names,
    purge_invalid_siblings,
    validate_report,
)

# MOPS 安全性阻擋頁的真實內容（2026Q2 存進 1,830 份的就是這個，共 800 bytes）。
BLOCK_PAGE = """<html>
<head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"></head>
<body>
因為安全性考量，您所執行的頁面無法呈現。<BR>
FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED.<BR>
錯誤代碼：7641438217039164268<BR>
</body>
</html>"""

NOT_PUBLISHED = (
    "<h4 align = 'center'><font color = 'red' "
    "style = 'line-height:30px;'>檔案不存在!</font></h4><br>"
)

RATE_LIMITED = "<html><body>OVERRUN - 查詢過於頻繁,請稍後再試</body></html>"


def make_report(size: int = MIN_REPORT_BYTES + 1000, marker_offset: int = 200) -> str:
    """組一份會通過驗證的假報表，marker 放在指定位移處。"""
    marker = 'xmlns:xbrli="http://www.xbrl.org/2003/instance"'
    head = "<html><head>" + ("<!-- pad -->" * (marker_offset // 12))
    body = head + marker + "</head><body>"
    return body + "x" * max(0, size - len(body.encode("utf-8"))) + "</body></html>"


# --- validate_report：存檔關卡 ---------------------------------------------


def test_block_page_is_rejected():
    assert validate_report(BLOCK_PAGE) == "too_small"


def test_not_published_page_is_rejected():
    assert validate_report(NOT_PUBLISHED) == "too_small"


def test_rate_limit_page_is_rejected():
    assert validate_report(RATE_LIMITED) == "too_small"


def test_valid_report_is_accepted():
    assert validate_report(make_report()) is None


def test_size_boundary():
    # 只差一個 byte 也要擋下來，確認門檻真的生效而不是被其他條件放行。
    marker = 'xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"'
    prefix = "<html>" + marker
    just_under = prefix + "x" * (MIN_REPORT_BYTES - len(prefix.encode("utf-8")) - 1)
    just_at = prefix + "x" * (MIN_REPORT_BYTES - len(prefix.encode("utf-8")))
    assert len(just_under.encode("utf-8")) == MIN_REPORT_BYTES - 1
    assert len(just_at.encode("utf-8")) == MIN_REPORT_BYTES
    assert validate_report(just_under) == "too_small"
    assert validate_report(just_at) is None


def test_large_page_without_xbrl_markers_is_rejected():
    # 夠大但不是報表 —— 光靠大小門檻擋不住，要靠 marker。
    page = "<html><body>" + "x" * (MIN_REPORT_BYTES + 100) + "</body></html>"
    assert validate_report(page) == "no_xbrl_markers"


def test_missing_html_tag_is_rejected():
    page = "xmlns:xbrli=http://www.xbrl.org/2003/instance " + "x" * MIN_REPORT_BYTES
    assert validate_report(page) == "invalid_html"


def test_cjk_report_size_measured_in_bytes():
    # 中文字在 utf-8 是 3 bytes。門檻若誤用字元數，這份會被錯放行。
    marker = 'xmlns:xbrli="http://www.xbrl.org/2003/instance"'
    page = "<html>" + marker + "資" * (MIN_REPORT_BYTES // 3 + 100)
    assert len(page) < MIN_REPORT_BYTES  # 字元數不足
    assert len(page.encode("utf-8")) > MIN_REPORT_BYTES  # 但 bytes 夠
    assert validate_report(page) is None


# --- classify_failure_reason：診斷訊息 --------------------------------------


def test_block_page_is_classified():
    assert classify_failure_reason(BLOCK_PAGE) == "page_not_accessible"


def test_block_page_wording_regression():
    """這是本次 bug 的回歸測試。

    舊版 marker 是 "the page can not be accessed" 與 "頁面無法執行"，
    而實際頁面寫的是 "this page ..." 與 "頁面無法呈現"，一字之差就漏判。
    兩種寫法現在都必須認得。
    """
    for wording in (
        "THIS PAGE CAN NOT BE ACCESSED",
        "the page can not be accessed",
        "頁面無法呈現",
        "頁面無法執行",
        "因為安全性考量",
    ):
        page = f"<html><body>{wording}</body></html>"
        assert classify_failure_reason(page) == "page_not_accessible", wording


def test_not_published_is_classified():
    assert classify_failure_reason(NOT_PUBLISHED) == "report_not_published"


def test_rate_limit_is_classified():
    assert classify_failure_reason(RATE_LIMITED) == "rate_limit"
    assert (
        classify_failure_reason("TOO MANY QUERY REQUESTS FROM YOUR IP") == "rate_limit"
    )


def test_valid_report_has_no_failure_reason():
    assert classify_failure_reason(make_report()) is None


def test_base_status_strips_retry_suffix():
    assert base_status("rate_limit;retries=0") == "rate_limit"
    assert base_status("ok") == "ok"


# --- is_valid_report_file / dedupe -----------------------------------------


def test_is_valid_report_file(tmp_path: Path):
    block = tmp_path / "2026Q2_1234_20260702.html"
    block.write_text(BLOCK_PAGE, encoding="utf-8")
    good = tmp_path / "2026Q1_1234_20260430.html"
    good.write_text(make_report(), encoding="utf-8")
    assert is_valid_report_file(block) is False
    assert is_valid_report_file(good) is True
    assert is_valid_report_file(tmp_path / "missing.html") is False


def test_is_valid_report_file_agrees_with_validate_report(tmp_path: Path):
    # marker 落在 HEAD_SCAN_BYTES 之後：便宜的檔頭掃描會漏，必須 fallback
    # 到 validate_report，否則這份報表會每晚被重抓一次。
    text = make_report(size=MIN_REPORT_BYTES + 50_000, marker_offset=40_000)
    path = tmp_path / "2026Q1_5678_20260430.html"
    path.write_text(text, encoding="utf-8")
    assert validate_report(text) is None
    assert is_valid_report_file(path) is True


def test_load_existing_report_names_ignores_invalid(tmp_path: Path):
    (tmp_path / "2026Q2_1111_20260702.html").write_text(BLOCK_PAGE, encoding="utf-8")
    (tmp_path / "2026Q2_2222_20260730.html").write_text(make_report(), encoding="utf-8")
    names = load_existing_report_names(tmp_path)
    # 壞檔不列入 dedupe key，下次執行才會重抓；好檔則不重抓。
    assert names == {"2026Q2_2222.html"}


# --- purge_invalid_siblings ------------------------------------------------


def test_purge_removes_only_invalid_siblings(tmp_path: Path):
    stale = tmp_path / "2026Q2_1234_20260702.html"
    stale.write_text(BLOCK_PAGE, encoding="utf-8")
    fresh = tmp_path / "2026Q2_1234_20260801.html"
    fresh.write_text(make_report(), encoding="utf-8")
    other = tmp_path / "2026Q2_9999_20260702.html"
    other.write_text(BLOCK_PAGE, encoding="utf-8")

    removed = purge_invalid_siblings(tmp_path, 2026, 2, "1234", keep=fresh)

    assert removed == [stale]
    assert not stale.exists()
    assert fresh.exists()
    # 別的 symbol 的壞檔不歸這次清理管。
    assert other.exists()


def test_purge_keeps_valid_siblings(tmp_path: Path):
    older = tmp_path / "2026Q2_1234_20260730.html"
    older.write_text(make_report(), encoding="utf-8")
    fresh = tmp_path / "2026Q2_1234_20260801.html"
    fresh.write_text(make_report(), encoding="utf-8")

    assert purge_invalid_siblings(tmp_path, 2026, 2, "1234", keep=fresh) == []
    assert older.exists()


def test_purge_does_not_touch_prefix_neighbours(tmp_path: Path):
    # glob 的前綴比對會掃到 2026Q2_1234X_...，regex 必須把它擋掉。
    neighbour = tmp_path / "2026Q2_12345_20260702.html"
    neighbour.write_text(BLOCK_PAGE, encoding="utf-8")
    fresh = tmp_path / "2026Q2_1234_20260801.html"
    fresh.write_text(make_report(), encoding="utf-8")

    assert purge_invalid_siblings(tmp_path, 2026, 2, "1234", keep=fresh) == []
    assert neighbour.exists()


# --- decide_exit_code：什麼情況該告警 ---------------------------------------


def test_exit_code_quarter_fully_collected():
    # 全部 skipped_exists：沒抓也沒失敗，正常。
    assert decide_exit_code(saved=0, fail=0, non_benign_fail=0, aborted=False) == 0


def test_exit_code_before_filing_deadline():
    # 申報期限前整批 report_not_published —— 良性，不該每晚告警。
    assert decide_exit_code(saved=0, fail=1800, non_benign_fail=0, aborted=False) == 0


def test_exit_code_transient_failures_among_benign():
    # 少數 curl 失敗混在一堆「還沒申報」裡，不告警。
    assert decide_exit_code(saved=0, fail=1800, non_benign_fail=3, aborted=False) == 0


def test_exit_code_systemic_failure():
    # 每一次抓取都因非良性原因失敗（例如 MOPS 改版）—— 這正是舊版會靜悄悄
    # 停擺的情境，必須回非 0。
    assert (
        decide_exit_code(saved=0, fail=1800, non_benign_fail=1800, aborted=False) == 1
    )


def test_exit_code_partial_success_is_ok():
    assert decide_exit_code(saved=5, fail=100, non_benign_fail=100, aborted=False) == 0


def test_exit_code_abort_always_fails():
    assert decide_exit_code(saved=50, fail=5, non_benign_fail=5, aborted=True) == 1


# --- 無 pytest 時的執行入口 -------------------------------------------------


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
