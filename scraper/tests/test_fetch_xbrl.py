"""fetch_xbrl 的回應驗證與失敗分類測試。

pytest 相容，但因為專案目前沒有安裝 pytest、CI 也沒跑（只跑 ruff），
本檔可以直接執行：

    venv/bin/python3 scraper/tests/test_fetch_xbrl.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "quarterly"))

import fetch_xbrl  # noqa: E402
from fetch_xbrl import (  # noqa: E402
    MIN_REPORT_BYTES,
    REPORT_ID_CONSOLIDATED,
    REPORT_ID_INDIVIDUAL,
    base_status,
    classify_failure_reason,
    decide_exit_code,
    is_saved_status,
    is_valid_report_file,
    load_existing_report_names,
    parse_run_date,
    purge_sibling_reports,
    resolve_report_ids,
    save_symbol_report,
    saved_status,
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


# --- purge_sibling_reports ------------------------------------------------


def test_purge_removes_only_invalid_siblings(tmp_path: Path):
    stale = tmp_path / "2026Q2_1234_20260702.html"
    stale.write_text(BLOCK_PAGE, encoding="utf-8")
    fresh = tmp_path / "2026Q2_1234_20260801.html"
    fresh.write_text(make_report(), encoding="utf-8")
    other = tmp_path / "2026Q2_9999_20260702.html"
    other.write_text(BLOCK_PAGE, encoding="utf-8")

    removed = purge_sibling_reports(tmp_path, 2026, 2, "1234", keep=fresh)

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

    assert purge_sibling_reports(tmp_path, 2026, 2, "1234", keep=fresh) == []
    assert older.exists()


def test_purge_removes_valid_siblings_when_forced(tmp_path: Path):
    # FORCE_REPROCESS 是刻意覆寫。舊的有效檔留著就湊成「同季同 symbol 兩個
    # html」，collect_strict_html_per_symbol() 會整季 raise。
    older = tmp_path / "2026Q2_1234_20260730.html"
    older.write_text(make_report(), encoding="utf-8")
    fresh = tmp_path / "2026Q2_1234_20260801.html"
    fresh.write_text(make_report(), encoding="utf-8")

    removed = purge_sibling_reports(
        tmp_path, 2026, 2, "1234", keep=fresh, include_valid=True
    )

    assert removed == [older]
    assert not older.exists()
    assert fresh.exists()


def test_force_refetch_with_new_run_date_leaves_one_file(tmp_path: Path):
    """回歸測試：--run-date 回補改後綴時新舊檔名必然不同。

    force 若不清有效舊檔，這個目錄會同時存在 _20200515 與 _20260816 兩份，
    整季轉檔當場中止 —— 而 --run-date 的用途正是回補歷史季別。
    """
    old = tmp_path / "2020Q1_1234_20200515.html"
    old.write_text(make_report(), encoding="utf-8")
    f = FakeFetcher({"C": make_report()})

    real_sleep = fetch_xbrl.time.sleep
    fetch_xbrl.time.sleep = lambda _s: None
    try:
        symbol, status = save_symbol_report(
            "1234",
            2020,
            1,
            "20260816",
            tmp_path,
            load_existing_report_names(tmp_path),
            force=True,
            fetcher=f,
        )
    finally:
        fetch_xbrl.time.sleep = real_sleep

    assert status == "ok"
    assert [p.name for p in tmp_path.glob("*.html")] == ["2020Q1_1234_20260816.html"]


def test_purge_does_not_touch_prefix_neighbours(tmp_path: Path):
    # glob 的前綴比對會掃到 2026Q2_1234X_...，regex 必須把它擋掉。
    neighbour = tmp_path / "2026Q2_12345_20260702.html"
    neighbour.write_text(BLOCK_PAGE, encoding="utf-8")
    fresh = tmp_path / "2026Q2_1234_20260801.html"
    fresh.write_text(make_report(), encoding="utf-8")

    assert purge_sibling_reports(tmp_path, 2026, 2, "1234", keep=fresh) == []
    assert neighbour.exists()


# --- parse_run_date：檔名後綴 = publish_time ---------------------------------


def test_parse_run_date_defaults_to_today():
    from datetime import datetime

    assert parse_run_date(None) == datetime.now().strftime("%Y%m%d")


def test_parse_run_date_accepts_explicit_date():
    # 回補歷史季別時要能把 publish_time 釘在該季申報期限，而不是回補當天。
    assert parse_run_date("20200515") == "20200515"


def test_parse_run_date_rejects_bad_format():
    for bad in ("abc", "2020-05-15", "202005", "202005151"):
        try:
            parse_run_date(bad)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad!r}")


def test_parse_run_date_rejects_impossible_date():
    # 過得了 \d{8} 卻不是合法日期 —— 不能讓它寫進檔名再變成 publish_time。
    for bad in ("20261332", "20260230", "20260000"):
        try:
            parse_run_date(bad)
        except ValueError:
            continue
        raise AssertionError(f"should reject {bad!r}")


# --- saved_status / is_saved_status ------------------------------------------


def test_saved_status_keeps_ok_for_consolidated():
    # 合併財報的狀態字串刻意不改，既有 log 與監控都吃 "ok"。
    assert saved_status(REPORT_ID_CONSOLIDATED) == "ok"


def test_saved_status_marks_individual():
    assert saved_status(REPORT_ID_INDIVIDUAL) == "ok_a"


def test_is_saved_status_covers_both():
    assert is_saved_status("ok")
    assert is_saved_status("ok_a")
    # 失敗與 skip 都不算存檔成功，否則 decide_exit_code 會誤判。
    for reason in ("skipped_exists", "report_not_published", "rate_limit", "error:x"):
        assert not is_saved_status(reason), reason


# --- resolve_report_ids：個體 fallback 的啟動門檻 ----------------------------


def test_fallback_disabled_early_in_window():
    """申報期限前不探 A —— 這是效能面的核心保護。

    窗口一開就是期限前 30 天，那幾夜幾乎整批 report_not_published
    （2026-08-01 有 1,763 檔）。每檔多一次請求加 3 秒間隔約多 88 分鐘，
    23:50 起跑會壓到 03:00 的 stock-daily-retry。
    """
    for coverage in (0.0, 0.04, 0.28, 0.53, 0.72):
        ids, note = resolve_report_ids("auto", coverage)
        assert ids == (REPORT_ID_CONSOLIDATED,), coverage
        assert "未啟用" in note


def test_fallback_enabled_at_tail_of_window():
    # 2026Q2 實測 08-15 覆蓋率 89%，正是 A 探測唯一有意義的時點。
    for coverage in (0.80, 0.89, 1.0):
        ids, note = resolve_report_ids("auto", coverage)
        assert ids == (REPORT_ID_CONSOLIDATED, REPORT_ID_INDIVIDUAL), coverage
        assert "啟用" in note


def test_explicit_report_id_ignores_coverage():
    # 回補歷史季別時目錄可能是空的（覆蓋率 0），不該被門檻擋住。
    assert resolve_report_ids(REPORT_ID_INDIVIDUAL, 0.0)[0] == (REPORT_ID_INDIVIDUAL,)
    assert resolve_report_ids(REPORT_ID_CONSOLIDATED, 0.99)[0] == (
        REPORT_ID_CONSOLIDATED,
    )


# --- save_symbol_report：REPORT_ID fallback ----------------------------------


class FakeFetcher:
    """依 REPORT_ID 回傳預先排好的回應，並記下呼叫順序。"""

    def __init__(self, by_report_id: dict[str, str]):
        self.by_report_id = by_report_id
        self.calls: list[str] = []

    def __call__(self, symbol, year, quarter, report_id):
        self.calls.append(report_id)
        return self.by_report_id[report_id].encode("utf-8")


def _save(tmp_path: Path, fetcher, **kwargs):
    """呼叫 save_symbol_report，並把 sleep 拿掉（fallback 之間有 3 秒間隔）。"""
    real_sleep = fetch_xbrl.time.sleep
    fetch_xbrl.time.sleep = lambda _s: None
    try:
        return save_symbol_report(
            "1234", 2026, 2, "20260816", tmp_path, set(), fetcher=fetcher, **kwargs
        )
    finally:
        fetch_xbrl.time.sleep = real_sleep


def test_consolidated_hit_does_not_probe_individual(tmp_path: Path):
    # 絕大多數 symbol 走這條；多打一次 A 等於整季請求量翻倍。
    f = FakeFetcher({"C": make_report()})
    assert _save(tmp_path, f) == ("1234", "ok")
    assert f.calls == ["C"]
    assert (tmp_path / "2026Q2_1234_20260816.html").exists()


def test_falls_back_to_individual_when_consolidated_missing(tmp_path: Path):
    # 本次 bug 的核心回歸測試：無子公司的公司只有個體財報。
    f = FakeFetcher({"C": NOT_PUBLISHED, "A": make_report()})
    assert _save(tmp_path, f) == ("1234", "ok_a")
    assert f.calls == ["C", "A"]
    # 檔名不帶報表別 —— processor 的「同季同 symbol 只能有一個 html」不受影響。
    assert (tmp_path / "2026Q2_1234_20260816.html").exists()


def test_both_report_ids_missing_stays_benign(tmp_path: Path):
    # 申報期限前整批如此，不該因為多試了一個報表別就變成非良性失敗。
    f = FakeFetcher({"C": NOT_PUBLISHED, "A": NOT_PUBLISHED})
    symbol, status = _save(tmp_path, f)
    assert f.calls == ["C", "A"]
    assert base_status(status) == "report_not_published"
    assert base_status(status) in fetch_xbrl.BENIGN_FAILURE_REASONS


def test_rate_limit_does_not_fall_back(tmp_path: Path):
    # 換 REPORT_ID 一樣會被擋，而且會拖慢 RATE_LIMIT_ABORT_STREAK 收手。
    f = FakeFetcher({"C": RATE_LIMITED, "A": make_report()})
    symbol, status = _save(tmp_path, f)
    assert f.calls == ["C"]
    assert base_status(status) == "rate_limit"


def test_block_page_does_not_fall_back(tmp_path: Path):
    f = FakeFetcher({"C": BLOCK_PAGE, "A": make_report()})
    symbol, status = _save(tmp_path, f)
    assert f.calls == ["C"]
    assert base_status(status) == "page_not_accessible"


def test_individual_only_chain_skips_consolidated(tmp_path: Path):
    # 回補早已過申報期限的歷史季別：C 必定不存在，跳過可省一半請求。
    f = FakeFetcher({"A": make_report()})
    assert _save(tmp_path, f, report_ids=("A",)) == ("1234", "ok_a")
    assert f.calls == ["A"]


def test_existing_valid_report_short_circuits_fetch(tmp_path: Path):
    (tmp_path / "2026Q2_1234_20260701.html").write_text(make_report(), encoding="utf-8")
    f = FakeFetcher({"C": make_report(), "A": make_report()})
    real_sleep = fetch_xbrl.time.sleep
    fetch_xbrl.time.sleep = lambda _s: None
    try:
        result = save_symbol_report(
            "1234",
            2026,
            2,
            "20260816",
            tmp_path,
            load_existing_report_names(tmp_path),
            fetcher=f,
        )
    finally:
        fetch_xbrl.time.sleep = real_sleep
    assert result == ("1234", "skipped_exists")
    assert f.calls == []


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
