"""OTC scraper 失敗路徑的可見性測試。

pytest 相容，但因為專案目前沒有安裝 pytest、CI 也沒跑（只跑 ruff），
本檔可以直接執行：

    venv/bin/python3 scraper/tests/test_fetch_daily_otc_logging.py

背景：2026-09-02 的 daily pipeline 因為 TPEx 的 margin_sbl 端點暫時性失敗
而整條停擺，但 scraper log 裡連一行相關訊息都沒有——`fetch_data()` 當時對
非 200、內容過小、以及例外三種情況一律靜默 return，只能靠事後的
check_outputs.py 比對檔案才知道少了什麼。

這個 guard 的價值在於「它會講話」，而失效方式跟它要防的 bug 一樣是靜默的，
所以測試重點放在**每一條失敗路徑都必須印出可辨識的原因**。
"""

import contextlib
import io
import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _install_container_only_stubs():
    """requests / urllib3 / bs4 只裝在 scraper 容器裡，host venv 沒有。

    這個測試打的是 fetch_data() 的分支邏輯，不需要真的 HTTP stack，
    所以注入剛好夠 import 過關的假模組，讓測試維持「host 直接跑」。
    """

    def _missing(name):
        """真的裝了就不要蓋掉——`not in sys.modules` 只代表「還沒被 import」，
        用它當條件會在有裝 requests 的機器上把假模組永久種進 sys.modules。"""
        try:
            __import__(name)
        except ImportError:
            return True
        return False

    if _missing("requests"):
        requests = types.ModuleType("requests")
        requests.get = None  # 每個 case 自己塞
        requests.post = None
        sys.modules["requests"] = requests

    if _missing("urllib3"):
        urllib3 = types.ModuleType("urllib3")
        exceptions = types.ModuleType("urllib3.exceptions")
        exceptions.InsecureRequestWarning = type(
            "InsecureRequestWarning", (Warning,), {}
        )
        urllib3.exceptions = exceptions
        urllib3.disable_warnings = lambda *a, **k: None
        sys.modules["urllib3"] = urllib3
        sys.modules["urllib3.exceptions"] = exceptions

    if _missing("bs4"):
        bs4 = types.ModuleType("bs4")
        bs4.BeautifulSoup = None
        sys.modules["bs4"] = bs4


_install_container_only_stubs()

from scraper.daily import fetch_daily_otc as otc  # noqa: E402

DATE = "20260902"
CATEGORY = "融券借券"  # -> margin_sbl，就是 2026-09-02 漏掉的那一支
ENG = "margin_sbl"


class FakeResponse:
    """`.text` 刻意**從 content 推導**，不讓 case 自己指定。

    TPEx 的 404 頁面 Content-Type 是裸的 `text/html`（沒有 charset），
    requests 依 HTTP 規範退回 ISO-8859-1，中文因此全變 mojibake。
    如果這裡讓 case 直接傳一個已解碼好的 str，就正好繞過了production 會踩到的
    那次解碼——測試會綠、線上卻永遠對不上 marker。
    """

    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content

    @property
    def text(self):
        return self.content.decode("latin-1", errors="ignore")


@contextlib.contextmanager
def _run(fake_get):
    """跑一次 fetch_data，回傳 (stdout 文字, 輸出目錄)。"""
    original_get = otc.requests.get
    otc.requests.get = fake_get
    buf = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(buf):
                otc.fetch_data(DATE, CATEGORY, tmp)
            yield buf.getvalue(), tmp
    finally:
        otc.requests.get = original_get


def _assert_mentions(out, *needles):
    assert out.strip(), "失敗時什麼都沒印——這正是 2026-09-02 那次的問題"
    for needle in needles:
        assert needle in out, f"訊息裡少了 {needle!r}，實際輸出：{out!r}"


def test_non_200_is_reported():
    with _run(lambda *a, **k: FakeResponse(status_code=503)) as (out, tmp):
        _assert_mentions(out, DATE, ENG, "Status code: 503")
        assert not list(Path(tmp).rglob("otc.csv"))


def test_tpex_404_page_is_reported():
    """TPEx 的 404 頁面：status 200、UTF-8、9954 bytes ——「大小」擋不住它。

    實測（2026-09-03，打 tpex.org.tw 上不存在的路徑）：
        status=200  Content-Type='text/html'  r.encoding='ISO-8859-1'
        len(content)≈10 KB   ← 遠超過 margin_sbl 的 5000 門檻
        '404 - 證券櫃檯買賣中心' in r.text                  -> False（mojibake）
        marker.encode('big5')  in r.content                -> False（頁面不是 big5）
        marker in r.content.decode('utf-8', 'ignore')      -> True
    擋不下來的話會怎樣（拿真實頁面實測過）：big5 解碼後照樣 parse 出 9702 bytes
    的亂碼 HTML 寫成 otc.csv，再被 check_outputs.py 的 (>=10 bytes, >=2 行) 放行
    送進 processor。
    """
    page = (
        '<!DOCTYPE html><html lang="zh-Hant-tw"><head>'
        "<title>404 - 證券櫃檯買賣中心</title>"
        '<meta charset="utf-8"></head><body>'
    ).encode("utf-8") + b"<p>padding</p>\n" * 800
    assert len(page) > 5000, "這個 case 的重點就是大小擋不住，太小就沒在測東西"
    with _run(lambda *a, **k: FakeResponse(content=page)) as (out, tmp):
        _assert_mentions(out, DATE, ENG, "404")
        assert not list(Path(tmp).rglob("otc.csv"))


def test_undersized_body_is_reported_with_sizes():
    # 融券借券 的門檻是 5000 bytes；給 10 bytes 模擬空回應。
    with _run(lambda *a, **k: FakeResponse(content=b"x" * 10)) as (out, tmp):
        _assert_mentions(out, DATE, ENG, "empty or no data", "10 bytes", "5000")
        assert not list(Path(tmp).rglob("otc.csv"))


def test_network_exception_is_reported_with_type():
    def boom(*a, **k):
        raise TimeoutError("connection timed out")

    with _run(boom) as (out, tmp):
        _assert_mentions(out, DATE, ENG, "Error fetching", "TimeoutError", "timed out")
        assert not list(Path(tmp).rglob("otc.csv"))


def test_success_still_writes_and_logs():
    rows = "股票代號,股票名稱,融券前日餘額\n" + "\n".join(
        f'="{i:04d}",測試,0' for i in range(1000)
    )
    body = rows.encode("big5")
    assert len(body) > 5000
    with _run(lambda *a, **k: FakeResponse(content=body)) as (out, tmp):
        assert f"OTC {ENG} saved." in out, out
        written = list(Path(tmp).rglob("otc.csv"))
        assert len(written) == 1, written
        text = written[0].read_text(encoding="utf-8-sig")
        assert '"0001","測試","0"' in text, text[:200]


def test_index_failure_reports_last_error():
    """指數行情走 JSON 分支：所有候選日期都失敗時要講出最後的原因。"""
    original_get = otc.requests.get

    def boom(*a, **k):
        raise ConnectionError("dns failure")

    otc.requests.get = boom
    buf = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(buf):
                otc.fetch_data(DATE, "指數行情", tmp)
    finally:
        otc.requests.get = original_get
    out = buf.getvalue()
    _assert_mentions(out, DATE, "Last error", "ConnectionError", "dns failure")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
