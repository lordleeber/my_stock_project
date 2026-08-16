"""convert_quarterly_reports_xbrl 的報表別判讀與淨利取數測試。

pytest 相容，但因為專案目前沒有安裝 pytest、CI 也沒跑（只跑 ruff），
本檔可以直接執行：

    venv/bin/python3 processor/tests/test_quarterly_reports_xbrl.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "quarterly"))

from convert_quarterly_reports_xbrl import (  # noqa: E402
    NET_INCOME_CODE_BY_REPORT_CATEGORY,
    NET_INCOME_CODE_CONSOLIDATED,
    NET_INCOME_CODE_INDIVIDUAL,
    REPORT_CATEGORY_CONSOLIDATED,
    REPORT_CATEGORY_INDIVIDUAL,
    REPORT_CATEGORY_RE,
    UnknownReportCategoryError,
    build_experiment_row,
    clean_value_text,
    extract_meta_from_raw_html,
    normalize_report_category,
)

# MOPS t164sb01 的實際輸出片段。tag 名稱在部分檔案是小寫（2021Q2_1519），
# 值也可能被斷行（同一檔），所以 regex 必須 IGNORECASE + DOTALL。
HTML_CONSOLIDATED = """<html><body>
<ix:nonNumeric contextRef="From20200101To20200331" name="tifrs-notes:CompanyChineseName">台灣積體電路製造股份有限公司</ix:nonNumeric>
<ix:nonNumeric contextRef="From20200101To20200331" name="tifrs-notes:ReportCategory">Consolidated report</ix:nonNumeric>
<ix:nonNumeric contextRef="From20200101To20200331" name="tifrs-notes:Market">Listed company</ix:nonNumeric>
</body></html>"""

HTML_INDIVIDUAL = HTML_CONSOLIDATED.replace(
    "Consolidated report", "Individual report"
).replace("台灣積體電路製造股份有限公司", "八貫企業股份有限公司")

# 值被斷行 + tag/屬性全小寫，取自 2021Q2_1519 的真實排版。
HTML_LINEBREAK_LOWERCASE = """<html><body>
\t\t<ix:nonnumeric contextref="From20210101To20210630"
name="tifrs-notes:ReportCategory">Consolidated \r
report</ix:nonnumeric> \t\t<ix:nonnumeric contextref="From20210101To20210630" \r
name="tifrs-notes:Market">Listed company</ix:nonnumeric>
</body></html>"""

HTML_UNKNOWN_CATEGORY = HTML_CONSOLIDATED.replace(
    "Consolidated report", "Combined report"
)

HTML_NO_CATEGORY = """<html><body>
<ix:nonNumeric contextRef="From20200101To20200331" name="tifrs-notes:Market">Listed company</ix:nonNumeric>
</body></html>"""


# --- normalize_report_category ---------------------------------------------


def test_normalize_report_category_consolidated():
    assert (
        normalize_report_category("Consolidated report") == REPORT_CATEGORY_CONSOLIDATED
    )


def test_normalize_report_category_individual():
    assert normalize_report_category("Individual report") == REPORT_CATEGORY_INDIVIDUAL


def test_normalize_report_category_is_case_insensitive():
    assert (
        normalize_report_category("CONSOLIDATED REPORT") == REPORT_CATEGORY_CONSOLIDATED
    )
    assert normalize_report_category("individual report") == REPORT_CATEGORY_INDIVIDUAL


def test_normalize_report_category_non_consolidated_is_individual():
    """ "Non-consolidated report" 含有 "consolidated" 子字串，必須判成個體。

    先比對 consolidated 會把它歸成合併、去取取不到的 8610，net_income 靜默落成
    NULL，而且分類「成功」了所以 UnknownReportCategoryError 也不會觸發。
    連字號／空白／連寫三種寫法都要涵蓋，漏掉哪一種都是同一個靜默失敗。
    """
    assert (
        normalize_report_category("Non-consolidated report")
        == REPORT_CATEGORY_INDIVIDUAL
    )
    assert (
        normalize_report_category("Nonconsolidated report")
        == REPORT_CATEGORY_INDIVIDUAL
    )
    assert (
        normalize_report_category("Non consolidated report")
        == REPORT_CATEGORY_INDIVIDUAL
    )
    assert (
        normalize_report_category("NON-CONSOLIDATED REPORT")
        == REPORT_CATEGORY_INDIVIDUAL
    )


def test_normalize_report_category_unknown_returns_empty():
    """判不出來就回空字串，交給呼叫端 raise —— 不猜、不預設成合併。"""
    assert normalize_report_category("Combined report") == ""
    assert normalize_report_category("") == ""
    assert normalize_report_category(None) == ""


# --- REPORT_CATEGORY_RE ------------------------------------------------------


def test_report_category_re_extracts_plain():
    m = REPORT_CATEGORY_RE.search(HTML_CONSOLIDATED)
    assert m is not None
    assert clean_value_text(m.group(1)) == "Consolidated report"


def test_report_category_re_handles_linebreak_and_lowercase_tags():
    """2021Q2_1519 的排版：值跨行、tag 小寫。少了 DOTALL 這裡會抓成 'Consolidated'。"""
    m = REPORT_CATEGORY_RE.search(HTML_LINEBREAK_LOWERCASE)
    assert m is not None
    assert clean_value_text(m.group(1)) == "Consolidated report"
    assert normalize_report_category(clean_value_text(m.group(1))) == (
        REPORT_CATEGORY_CONSOLIDATED
    )


def test_report_category_re_absent_returns_none():
    assert REPORT_CATEGORY_RE.search(HTML_NO_CATEGORY) is None


# --- 取數對照表 --------------------------------------------------------------


def test_net_income_code_mapping():
    """個體財報沒有 8610（無非控制權益可拆），取 8200。"""
    assert (
        NET_INCOME_CODE_BY_REPORT_CATEGORY[REPORT_CATEGORY_CONSOLIDATED]
        == NET_INCOME_CODE_CONSOLIDATED
        == "8610"
    )
    assert (
        NET_INCOME_CODE_BY_REPORT_CATEGORY[REPORT_CATEGORY_INDIVIDUAL]
        == NET_INCOME_CODE_INDIVIDUAL
        == "8200"
    )


def test_net_income_code_mapping_has_no_default():
    assert NET_INCOME_CODE_BY_REPORT_CATEGORY.get("") is None
    assert NET_INCOME_CODE_BY_REPORT_CATEGORY.get("combined") is None


# --- extract_meta_from_raw_html ---------------------------------------------


def test_extract_meta_from_raw_html(tmp_path: Path):
    p = tmp_path / "2020Q1_1342_20200515.html"
    p.write_text(HTML_INDIVIDUAL, encoding="utf-8")
    name, market, report_category = extract_meta_from_raw_html(p)
    assert name == "八貫企業股份有限公司"
    assert market == "Listed company"
    assert report_category == "Individual report"


def test_extract_meta_from_raw_html_missing_category(tmp_path: Path):
    p = tmp_path / "2020Q1_1342_20200515.html"
    p.write_text(HTML_NO_CATEGORY, encoding="utf-8")
    _, _, report_category = extract_meta_from_raw_html(p)
    assert report_category == ""


# --- build_experiment_row ----------------------------------------------------

QUARTER = "2020Q1"
SYMBOL = "1342"
PUBLISH = "20200515"


def _wide_csv(path: Path, period: str, pairs: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["date", "symbol", "publish_time", "period"]
    values = [QUARTER, SYMBOL, PUBLISH, period]
    for i, (code, value) in enumerate(pairs.items(), start=1):
        header += [f"code{i}", f"value{i}"]
        values += [code, value]
    path.write_text(",".join(header) + "\n" + ",".join(values) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path, html: str, income_codes: dict[str, str]):
    processed = tmp_path / "processed"
    raw = tmp_path / "raw"
    inc_dir = processed / "income_statement_xbrl" / "2020" / QUARTER
    _wide_csv(inc_dir / "all_quarter.csv", "20200101-20200331", income_codes)
    _wide_csv(inc_dir / "all_accumulated.csv", "20200101-20200331", income_codes)
    _wide_csv(
        processed / "balance_sheet_xbrl" / "2020" / QUARTER / "all.csv",
        "20200331",
        {
            "1XXX": "1000000",
            "11XX": "600000",
            "130X": "100000",
            "21XX": "300000",
            "3XXX": "700000",
            "3110": "619653",
        },
    )
    _wide_csv(
        processed / "cash_flow_xbrl" / "2020" / QUARTER / "all_accumulated.csv",
        "20200101-20200331",
        {"AAAA": "1"},
    )
    html_dir = raw / "2020" / QUARTER
    html_dir.mkdir(parents=True, exist_ok=True)
    (html_dir / f"{QUARTER}_{SYMBOL}_{PUBLISH}.html").write_text(html, encoding="utf-8")
    return processed, raw


def test_build_row_individual_takes_8200(tmp_path: Path):
    processed, raw = _fixture(
        tmp_path,
        HTML_INDIVIDUAL,
        {"4000": "384877", "6900": "67889", "7900": "74130", "8200": "59105"},
    )
    row = build_experiment_row(processed, raw, QUARTER, SYMBOL)
    assert row["report_category"] == REPORT_CATEGORY_INDIVIDUAL
    assert row["net_income_q"] == 59105.0
    assert row["net_income_acc"] == 59105.0


def test_build_row_consolidated_takes_8610_not_8200(tmp_path: Path):
    """合併財報同時有 8200 與 8610，必須取 8610（已扣非控制權益）。"""
    processed, raw = _fixture(
        tmp_path,
        HTML_CONSOLIDATED,
        {
            "4000": "384877",
            "6900": "67889",
            "7900": "74130",
            "8200": "60000",
            "8610": "59105",
        },
    )
    row = build_experiment_row(processed, raw, QUARTER, SYMBOL)
    assert row["report_category"] == REPORT_CATEGORY_CONSOLIDATED
    assert row["net_income_q"] == 59105.0


def test_build_row_unknown_category_raises(tmp_path: Path):
    """來源冒出第三種值時要停下來，不能悄悄退回合併基礎把 net_income 寫成 NULL。"""
    processed, raw = _fixture(
        tmp_path,
        HTML_UNKNOWN_CATEGORY,
        {"4000": "384877", "8200": "59105", "8610": "59105"},
    )
    try:
        build_experiment_row(processed, raw, QUARTER, SYMBOL)
    except UnknownReportCategoryError as e:
        assert "Combined report" in str(e)
    else:
        raise AssertionError("expected UnknownReportCategoryError")


def test_build_row_missing_category_raises(tmp_path: Path):
    processed, raw = _fixture(
        tmp_path, HTML_NO_CATEGORY, {"4000": "384877", "8610": "59105"}
    )
    try:
        build_experiment_row(processed, raw, QUARTER, SYMBOL)
    except UnknownReportCategoryError:
        pass
    else:
        raise AssertionError("expected UnknownReportCategoryError")


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
