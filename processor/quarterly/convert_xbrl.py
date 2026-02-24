import csv
import html
import os
import re
import sys
from datetime import date
from datetime import datetime
from pathlib import Path
from collections import defaultdict


CATEGORY = "xbrl"
BALANCE_CATEGORY = "balance_sheet_xbrl"
INCOME_CATEGORY = "income_statement_xbrl"
CASHFLOW_CATEGORY = "cash_flow_xbrl"
EQUITY_CATEGORY = "equity_changes_xbrl"
RAW_DIR = os.environ.get("RAW_DIR", "data/raw")
PROCESSED_DIR = os.environ.get("PROCESSED_DIR", "data/processed")

STATEMENT_COLUMNS = [
    "date",
    "symbol",
    "account_code",
    "value_text",
    "value_num",
]

FILE_RE = re.compile(r"^(?P<date>\d{4}Q[1-4])_(?P<symbol>\d{4})\.html$")
FACT_RE = re.compile(r"<ix:(nonFraction|nonNumeric)\b([^>]*)>(.*?)</ix:\1>", re.IGNORECASE | re.DOTALL)
ATTR_RE = re.compile(r'([:\w-]+)\s*=\s*([\'"])(.*?)\2', re.DOTALL)
CONTEXT_RE = re.compile(
    r"<xbrli:context\b[^>]*\bid=['\"]([^'\"]+)['\"][^>]*>(.*?)</xbrli:context>",
    re.IGNORECASE | re.DOTALL,
)
COMPANY_RE = re.compile(
    r"<ix:nonNumeric\b[^>]*\bname=['\"]tifrs-notes:CompanyChineseName['\"][^>]*>(.*?)</ix:nonNumeric>",
    re.IGNORECASE | re.DOTALL,
)
COMPANY_ID_RE = re.compile(
    r"<ix:nonNumeric\b[^>]*\bname=['\"]tifrs-notes:CompanyID['\"][^>]*>(.*?)</ix:nonNumeric>",
    re.IGNORECASE | re.DOTALL,
)
MARKET_RE = re.compile(
    r"<ix:nonNumeric\b[^>]*\bname=['\"]tifrs-notes:Market['\"][^>]*>(.*?)</ix:nonNumeric>",
    re.IGNORECASE | re.DOTALL,
)

CASHFLOW_FACT_NAME_HINTS = (
    "cashflows",
    "cashflow",
    "cashandcashequivalentsatbeginningofperiod",
    "cashandcashequivalentsatendofperiod",
    "increasedecreaseincashandcashequivalents",
)


def read_html_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp950", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def get_error_log_path() -> Path:
    app_log = Path("/app/error_processor.log")
    return app_log if app_log.parent.exists() else Path("error_processor.log")


def log_duplicate_and_exit(category: str, row: dict[str, str]):
    error_log = get_error_log_path()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with error_log.open("a", encoding="utf-8") as f:
        f.write(f"\n[{ts}] duplicate row detected in {category}\n")
        f.write(
            "key="
            f"date={row.get('date','')},symbol={row.get('symbol','')},"
            f"account_code={row.get('account_code','')},value_text={row.get('value_text','')},value_num={row.get('value_num','')}\n"
        )
    print(f"Error: duplicate row detected in {category}. See {error_log}")
    raise SystemExit(1)


def write_wide_all_csv(output_path: Path, rows: list[dict[str, str]]):
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("date", ""), row.get("symbol", ""))].append(row)

    max_pairs = max((len(v) for v in grouped.values()), default=0)
    category = output_path.parts[-4] if len(output_path.parts) >= 4 else ""
    header = ["date", "symbol", "period"]
    for i in range(1, max_pairs + 1):
        header.extend([f"code{i}", f"value{i}"])

    def _period_text(date_str: str) -> str:
        year = int(date_str[:4])
        q = int(date_str[5])
        if q == 1:
            q_start = "0101"
            q_end = "0331"
        elif q == 2:
            q_start = "0401"
            q_end = "0630"
        elif q == 3:
            q_start = "0701"
            q_end = "0930"
        else:
            q_start = "1001"
            q_end = "1231"
        y_start = f"{year}0101"
        q_start_date = f"{year}{q_start}"
        q_end_date = f"{year}{q_end}"

        if category == BALANCE_CATEGORY:
            return q_end_date
        if category == CASHFLOW_CATEGORY:
            return f"{y_start}-{q_end_date}"
        return f"{q_start_date}-{q_end_date}"

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for (date_str, symbol), items in sorted(grouped.items()):
            items_sorted = sorted(items, key=lambda x: x.get("account_code", ""))
            out = [date_str, symbol, _period_text(date_str)]
            for item in items_sorted:
                out.append(item.get("account_code", ""))
                out.append(item.get("value_num", "") or item.get("value_text", ""))
            if len(items_sorted) < max_pairs:
                out.extend(["", ""] * (max_pairs - len(items_sorted)))
            writer.writerow(out)


def is_blocked_page(html_text: str) -> bool:
    lower = html_text.lower()
    return "the page can not be accessed" in lower or "頁面無法執行" in html_text


def clean_value_text(raw_value: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw_value)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def normalize_account_name(name: str) -> str:
    if not name:
        return ""
    s = name.replace("\u3000", " ").strip()
    s = re.sub(r"\s+", " ", s)
    # Strip leading/trailing punctuation-like noise from table rendering.
    s = re.sub(r"^[\s,.;:，。；：、·‧•]+", "", s)
    s = re.sub(r"[\s,.;:，。；：、·‧•]+$", "", s)
    return s.strip()


def parse_attrs(attr_blob: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for key, _, value in ATTR_RE.findall(attr_blob):
        attrs[key] = html.unescape(value).strip()
    return attrs


def parse_account_names(cell_html: str) -> tuple[str, str]:
    zh_m = re.search(r'<span class="zh">(.*?)</span>', cell_html, re.IGNORECASE | re.DOTALL)
    en_m = re.search(r'<span class="en">(.*?)</span>', cell_html, re.IGNORECASE | re.DOTALL)
    zh = normalize_account_name(clean_value_text(zh_m.group(1)) if zh_m else clean_value_text(cell_html))
    en = normalize_account_name(clean_value_text(en_m.group(1)) if en_m else "")
    return zh, en


def parse_numeric(value_text: str, sign: str, fact_type: str) -> str:
    if fact_type.lower() != "nonfraction":
        return ""
    if not value_text or value_text in {"--", "-"}:
        return ""
    s = value_text.replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        value = float(s)
        if sign == "-" and value > 0:
            value = -value
        return str(value)
    except ValueError:
        return ""


def extract_company_name(html_text: str) -> str:
    m = COMPANY_RE.search(html_text)
    if not m:
        return ""
    return clean_value_text(m.group(1))


def extract_company_id(html_text: str) -> str:
    m = COMPANY_ID_RE.search(html_text)
    if not m:
        return ""
    return clean_value_text(m.group(1))


def extract_market(html_text: str) -> str:
    m = MARKET_RE.search(html_text)
    if not m:
        return ""
    return clean_value_text(m.group(1))


def build_context_map(html_text: str) -> dict[str, str]:
    return {ctx_id: body for ctx_id, body in CONTEXT_RE.findall(html_text)}


def classify_statement(fact_name: str, fact_type: str, context_ref: str, context_body: str) -> str | None:
    if fact_type.lower() != "nonfraction":
        return None
    if context_ref.startswith("AsOf"):
        return BALANCE_CATEGORY
    if "ComponentsOfEquityAxis" in context_body:
        return EQUITY_CATEGORY

    lname = fact_name.lower()
    if lname.startswith("tifrs-scf:"):
        return CASHFLOW_CATEGORY
    if any(k in lname for k in CASHFLOW_FACT_NAME_HINTS):
        return CASHFLOW_CATEGORY
    return INCOME_CATEGORY


def get_section_ranges(html_text: str) -> dict[str, tuple[int, int]]:
    ranges: dict[str, tuple[int, int]] = {}

    def _range(start_pat: str, end_pat: str, key: str):
        start_m = re.search(start_pat, html_text, re.IGNORECASE)
        if not start_m:
            return
        start = start_m.end()
        end_m = re.search(end_pat, html_text[start:], re.IGNORECASE)
        end = start + end_m.start() if end_m else len(html_text)
        ranges[key] = (start, end)

    _range(r'<div id="BalanceSheet"></div>', r'<div id="StatementOfComprehensiveIncome"></div>', BALANCE_CATEGORY)
    _range(r'<div id="StatementOfComprehensiveIncome"></div>', r'<div id="StatementsOfCashFlows"></div>', INCOME_CATEGORY)
    _range(r'<div id="StatementsOfCashFlows"></div>', r'<div id="StatementsOfChangeInEquity"></div>', CASHFLOW_CATEGORY)
    _range(r'<div id="StatementsOfChangeInEquity"></div>', r'<div id="ReportOfIndependentAuditors"></div>', EQUITY_CATEGORY)
    return ranges


def classify_by_position(pos: int, section_ranges: dict[str, tuple[int, int]]) -> str | None:
    for cat in (BALANCE_CATEGORY, INCOME_CATEGORY, CASHFLOW_CATEGORY, EQUITY_CATEGORY):
        r = section_ranges.get(cat)
        if not r:
            continue
        if r[0] <= pos < r[1]:
            return cat
    return None


def quarter_range(date_str: str) -> tuple[str, str]:
    year = int(date_str[:4])
    q = int(date_str[5])
    if q == 1:
        start = date(year, 1, 1)
        end = date(year, 3, 31)
    elif q == 2:
        start = date(year, 4, 1)
        end = date(year, 6, 30)
    elif q == 3:
        start = date(year, 7, 1)
        end = date(year, 9, 30)
    else:
        start = date(year, 10, 1)
        end = date(year, 12, 31)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def keep_current_period_row(statement_category: str, context_ref: str, date_str: str) -> bool:
    q_start, q_end = quarter_range(date_str)
    y_start = f"{date_str[:4]}0101"

    m_asof = re.match(r"^AsOf(\d{8})", context_ref)
    if m_asof:
        if statement_category == EQUITY_CATEGORY:
            # Equity changes table needs both beginning-of-year and quarter-end snapshots.
            return m_asof.group(1) in {y_start, q_end}
        return statement_category in (BALANCE_CATEGORY, CASHFLOW_CATEGORY) and m_asof.group(1) == q_end

    m_from = re.match(r"^From(\d{8})To(\d{8})", context_ref)
    if not m_from:
        return False
    start, end = m_from.group(1), m_from.group(2)
    if end != q_end:
        return False

    if statement_category == INCOME_CATEGORY:
        # Keep single-quarter values only.
        return start == q_start
    if statement_category in (CASHFLOW_CATEGORY, EQUITY_CATEGORY):
        # Interim reports are generally presented YTD to quarter-end.
        return start == y_start
    return False


def extract_income_statement_code_map(html_text: str) -> tuple[dict[tuple[str, str, str], tuple[str, str]], dict[str, tuple[str, str]]]:
    """
    Build mapping from (fact_name, context_ref, value_text) -> (account_code, account_name)
    only for Statement of Comprehensive Income section.
    """
    key_map: dict[tuple[str, str, str], tuple[str, str]] = {}
    codebook: dict[str, tuple[str, str]] = {}

    start_m = re.search(r'<div id="StatementOfComprehensiveIncome"></div>', html_text, re.IGNORECASE)
    if not start_m:
        return key_map, codebook
    start = start_m.end()

    # Income statement ends when cash flow section starts.
    end_markers = [
        re.search(r'<div id="StatementsOfCashFlows"></div>', html_text[start:], re.IGNORECASE),
        re.search(r'Statements of Cash Flows', html_text[start:], re.IGNORECASE),
    ]
    end_offsets = [m.start() for m in end_markers if m]
    end = start + min(end_offsets) if end_offsets else len(html_text)
    section = html_text[start:end]

    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", section, re.IGNORECASE | re.DOTALL):
        tds = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.IGNORECASE | re.DOTALL)
        if len(tds) < 2:
            continue

        account_code = clean_value_text(tds[0])
        if not re.match(r"^[0-9A-Z]{4}$", account_code):
            continue

        account_name, account_name_en = parse_account_names(tds[1])
        codebook[account_code] = (account_name, account_name_en)

        for fact_m in FACT_RE.finditer(tr):
            attrs = parse_attrs(fact_m.group(2))
            fact_name = attrs.get("name", "")
            context_ref = attrs.get("contextRef", "")
            value_text = clean_value_text(fact_m.group(3))
            if fact_name and context_ref and value_text:
                key_map[(fact_name, context_ref, value_text)] = (account_code, account_name)

    return key_map, codebook


def extract_balance_sheet_code_map(html_text: str) -> tuple[dict[tuple[str, str, str], tuple[str, str]], dict[str, tuple[str, str]]]:
    """
    Balance sheet section is from #BalanceSheet to #StatementOfComprehensiveIncome.
    """
    key_map: dict[tuple[str, str, str], tuple[str, str]] = {}
    codebook: dict[str, tuple[str, str]] = {}
    start_m = re.search(r'<div id="BalanceSheet"></div>', html_text, re.IGNORECASE)
    if not start_m:
        return key_map, codebook
    start = start_m.end()

    end_m = re.search(r'<div id="StatementOfComprehensiveIncome"></div>', html_text[start:], re.IGNORECASE)
    end = start + end_m.start() if end_m else len(html_text)
    section = html_text[start:end]

    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", section, re.IGNORECASE | re.DOTALL):
        tds = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.IGNORECASE | re.DOTALL)
        if len(tds) < 2:
            continue
        account_code = clean_value_text(tds[0])
        if not re.match(r"^[0-9A-Z]{4}$", account_code):
            continue
        account_name, account_name_en = parse_account_names(tds[1])
        codebook[account_code] = (account_name, account_name_en)

        for fact_m in FACT_RE.finditer(tr):
            attrs = parse_attrs(fact_m.group(2))
            fact_name = attrs.get("name", "")
            context_ref = attrs.get("contextRef", "")
            value_text = clean_value_text(fact_m.group(3))
            if fact_name and context_ref and value_text:
                key_map[(fact_name, context_ref, value_text)] = (account_code, account_name)
    return key_map, codebook


def extract_cash_flow_code_map(html_text: str) -> tuple[dict[tuple[str, str, str], tuple[str, str]], dict[str, tuple[str, str]]]:
    """
    Cash flow section is from #StatementsOfCashFlows to #StatementsOfChangeInEquity.
    """
    key_map: dict[tuple[str, str, str], tuple[str, str]] = {}
    codebook: dict[str, tuple[str, str]] = {}
    start_m = re.search(r'<div id="StatementsOfCashFlows"></div>', html_text, re.IGNORECASE)
    if not start_m:
        return key_map, codebook
    start = start_m.end()

    end_m = re.search(r'<div id="StatementsOfChangeInEquity"></div>', html_text[start:], re.IGNORECASE)
    end = start + end_m.start() if end_m else len(html_text)
    section = html_text[start:end]

    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", section, re.IGNORECASE | re.DOTALL):
        tds = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.IGNORECASE | re.DOTALL)
        if len(tds) < 2:
            continue
        account_code = clean_value_text(tds[0])
        if not re.match(r"^(?:[A-Z]{4}|[A-Z]\d{4,5})$", account_code):
            continue
        account_name, account_name_en = parse_account_names(tds[1])
        codebook[account_code] = (account_name, account_name_en)

        for fact_m in FACT_RE.finditer(tr):
            attrs = parse_attrs(fact_m.group(2))
            fact_name = attrs.get("name", "")
            context_ref = attrs.get("contextRef", "")
            value_text = clean_value_text(fact_m.group(3))
            if fact_name and context_ref and value_text:
                key_map[(fact_name, context_ref, value_text)] = (account_code, account_name)
    return key_map, codebook


def extract_equity_changes_code_map(html_text: str) -> tuple[dict[tuple[str, str, str], tuple[str, str]], dict[str, tuple[str, str]]]:
    """
    Equity changes section is from #StatementsOfChangeInEquity to #ReportOfIndependentAuditors.
    """
    key_map: dict[tuple[str, str, str], tuple[str, str]] = {}
    codebook: dict[str, tuple[str, str]] = {}
    start_m = re.search(r'<div id="StatementsOfChangeInEquity"></div>', html_text, re.IGNORECASE)
    if not start_m:
        return key_map, codebook
    start = start_m.end()

    end_m = re.search(r'<div id="ReportOfIndependentAuditors"></div>', html_text[start:], re.IGNORECASE)
    end = start + end_m.start() if end_m else len(html_text)
    section = html_text[start:end]

    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", section, re.IGNORECASE | re.DOTALL):
        tds = re.findall(r"<td\b[^>]*>(.*?)</td>", tr, re.IGNORECASE | re.DOTALL)
        if len(tds) < 2:
            continue
        account_code = clean_value_text(tds[0])
        if not re.match(r"^[A-Z0-9]{1,5}$", account_code):
            continue
        account_name, account_name_en = parse_account_names(tds[1])
        codebook[account_code] = (account_name, account_name_en)

        for fact_m in FACT_RE.finditer(tr):
            attrs = parse_attrs(fact_m.group(2))
            fact_name = attrs.get("name", "")
            context_ref = attrs.get("contextRef", "")
            value_text = clean_value_text(fact_m.group(3))
            if fact_name and context_ref and value_text:
                key_map[(fact_name, context_ref, value_text)] = (account_code, account_name)
    return key_map, codebook


def iter_fact_rows(date_str: str, symbol: str, html_text: str):
    company_id = extract_company_id(html_text)
    company_name = extract_company_name(html_text)
    market = extract_market(html_text)
    context_map = build_context_map(html_text)
    section_ranges = get_section_ranges(html_text)
    income_code_map, income_codebook = extract_income_statement_code_map(html_text)
    balance_code_map, balance_codebook = extract_balance_sheet_code_map(html_text)
    cashflow_code_map, cashflow_codebook = extract_cash_flow_code_map(html_text)
    equity_code_map, equity_codebook = extract_equity_changes_code_map(html_text)
    for m in FACT_RE.finditer(html_text):
        fact_type = m.group(1)
        attrs = parse_attrs(m.group(2))
        value_text = clean_value_text(m.group(3))
        if not value_text:
            continue
        sign = attrs.get("sign", "")
        context_ref = attrs.get("contextRef", "")
        fact_name = attrs.get("name", "")
        context_body = context_map.get(context_ref, "")
        row = {
            "date": date_str,
            "symbol": symbol,
            "company_id": company_id,
            "name": company_name,
            "market": market,
            "account_code": "",
            "account_name": "",
            "fact_name": fact_name,
            "fact_type": fact_type,
            "context_ref": context_ref,
            "unit_ref": attrs.get("unitRef", ""),
            "decimals": attrs.get("decimals", ""),
            "scale": attrs.get("scale", ""),
            "sign": sign,
            "value_text": value_text,
            "value_num": parse_numeric(value_text, sign, fact_type),
        }
        pos_category = classify_by_position(m.start(), section_ranges)
        statement_category = pos_category
        if statement_category is None:
            statement_category = classify_statement(fact_name, fact_type, context_ref, context_body)
        key = (fact_name, context_ref, value_text)
        if pos_category == CASHFLOW_CATEGORY and key in cashflow_code_map:
            statement_category = CASHFLOW_CATEGORY
        if statement_category == INCOME_CATEGORY:
            mapped = income_code_map.get(key)
            if mapped:
                row["account_code"] = mapped[0]
                row["account_name"] = mapped[1]
        elif statement_category == BALANCE_CATEGORY:
            mapped = balance_code_map.get(key)
            if mapped:
                row["account_code"] = mapped[0]
                row["account_name"] = mapped[1]
        elif statement_category == CASHFLOW_CATEGORY:
            mapped = cashflow_code_map.get(key)
            if mapped:
                row["account_code"] = mapped[0]
                row["account_name"] = mapped[1]
        elif statement_category == EQUITY_CATEGORY:
            mapped = equity_code_map.get(key)
            if mapped:
                row["account_code"] = mapped[0]
                row["account_name"] = mapped[1]
        yield row, statement_category, income_codebook, balance_codebook, cashflow_codebook, equity_codebook


def main():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    quarter_pattern = r"^\d{4}Q[1-4]$"

    if not start_env or not end_env:
        print("Error: START_DATE and END_DATE are both required (YYYYQX).")
        print("Example: START_DATE=2024Q1 END_DATE=2024Q1 python convert_quarterly.py")
        sys.exit(1)
    if not (re.match(quarter_pattern, start_env) and re.match(quarter_pattern, end_env)):
        print(f"Error: Invalid quarter format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYQX.")
        sys.exit(1)
    if start_env > end_env:
        print(f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env}).")
        sys.exit(1)

    raw_path = Path(RAW_DIR) / CATEGORY
    if not raw_path.exists():
        print(f"Skip: raw path not found: {raw_path}")
        return

    unified_codebook: dict[tuple[str, str], tuple[str, str]] = {}
    codebook_path = Path(PROCESSED_DIR) / "xbrl_codebook.csv"

    # Load existing xbrl codebook first, then merge current-run findings.
    if codebook_path.exists():
        try:
            with codebook_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    statement_type = (row.get("statement_type") or "").strip()
                    account_code = (row.get("account_code") or "").strip()
                    if not statement_type or not account_code:
                        continue
                    name_zh = normalize_account_name((row.get("account_name_zh") or "").strip())
                    name_en = normalize_account_name((row.get("account_name_en") or "").strip())
                    unified_codebook[(statement_type, account_code)] = (name_zh, name_en)
        except Exception as e:
            print(f"[WARN] Failed to load existing codebook {codebook_path}: {e}")

    for date_dir in sorted(raw_path.rglob("????Q[1-4]")):
        date_str = date_dir.name
        if date_str < start_env or date_str > end_env:
            continue

        output_paths = {
            BALANCE_CATEGORY: Path(PROCESSED_DIR) / BALANCE_CATEGORY / date_str[:4] / date_str / "all.csv",
            INCOME_CATEGORY: Path(PROCESSED_DIR) / INCOME_CATEGORY / date_str[:4] / date_str / "all.csv",
            CASHFLOW_CATEGORY: Path(PROCESSED_DIR) / CASHFLOW_CATEGORY / date_str[:4] / date_str / "all.csv",
        }
        for output_path in output_paths.values():
            output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Processing {CATEGORY} {date_str}...")
        total_files = 0
        blocked_files = 0
        fact_rows_by_category = {
            BALANCE_CATEGORY: 0,
            INCOME_CATEGORY: 0,
            CASHFLOW_CATEGORY: 0,
        }
        emitted_keys = {
            BALANCE_CATEGORY: set(),
            INCOME_CATEGORY: set(),
            CASHFLOW_CATEGORY: set(),
        }
        income_codebook_by_symbol: dict[str, dict[str, tuple[str, str]]] = {}
        balance_codebook_by_symbol: dict[str, dict[str, tuple[str, str]]] = {}
        cashflow_codebook_by_symbol: dict[str, dict[str, tuple[str, str]]] = {}

        statement_rows_by_category = {
            BALANCE_CATEGORY: [],
            INCOME_CATEGORY: [],
            CASHFLOW_CATEGORY: [],
        }

        try:
            for html_path in sorted(date_dir.glob("*.html")):
                total_files += 1
                m = FILE_RE.match(html_path.name)
                if not m:
                    continue
                symbol = m.group("symbol")
                try:
                    html_text = read_html_text(html_path)
                    if is_blocked_page(html_text):
                        blocked_files += 1
                        continue
                    for row, statement_category, income_codebook, balance_codebook, cashflow_codebook, equity_codebook in iter_fact_rows(date_str, symbol, html_text):
                        if income_codebook:
                            income_codebook_by_symbol[symbol] = income_codebook
                        if balance_codebook:
                            balance_codebook_by_symbol[symbol] = balance_codebook
                        if cashflow_codebook:
                            cashflow_codebook_by_symbol[symbol] = cashflow_codebook
                        if statement_category in (BALANCE_CATEGORY, INCOME_CATEGORY, CASHFLOW_CATEGORY):
                            if not keep_current_period_row(statement_category, row.get("context_ref", ""), date_str):
                                continue
                            if not row.get("account_code"):
                                continue
                            statement_row = {k: row.get(k, "") for k in STATEMENT_COLUMNS}
                            # Use context_ref internally for duplicate detection to avoid false positives
                            # when different equity columns happen to share the same visible value.
                            dedup_key = (
                                statement_row.get("date", ""),
                                statement_row.get("symbol", ""),
                                statement_row.get("account_code", ""),
                                statement_row.get("value_text", ""),
                                statement_row.get("value_num", ""),
                                row.get("context_ref", ""),
                            )
                            if dedup_key in emitted_keys[statement_category]:
                                log_duplicate_and_exit(statement_category, statement_row)
                            emitted_keys[statement_category].add(dedup_key)
                            statement_rows_by_category[statement_category].append(statement_row)
                            fact_rows_by_category[statement_category] += 1
                except Exception as e:
                    print(f"  [WARN] failed to parse {html_path}: {e}")
        finally:
            pass

        write_wide_all_csv(output_paths[BALANCE_CATEGORY], statement_rows_by_category[BALANCE_CATEGORY])
        write_wide_all_csv(output_paths[INCOME_CATEGORY], statement_rows_by_category[INCOME_CATEGORY])
        write_wide_all_csv(output_paths[CASHFLOW_CATEGORY], statement_rows_by_category[CASHFLOW_CATEGORY])

        print(f"  Files={total_files}, blocked={blocked_files}")
        print(f"  [+] Saved {output_paths[BALANCE_CATEGORY]} (facts={fact_rows_by_category[BALANCE_CATEGORY]})")
        print(f"  [+] Saved {output_paths[INCOME_CATEGORY]} (facts={fact_rows_by_category[INCOME_CATEGORY]})")
        print(f"  [+] Saved {output_paths[CASHFLOW_CATEGORY]} (facts={fact_rows_by_category[CASHFLOW_CATEGORY]})")

        def _merge_codebook(statement_type: str, codebook_by_symbol: dict[str, dict[str, tuple[str, str]]]):
            merged: dict[str, tuple[str, str]] = {}
            for _, codebook in sorted(codebook_by_symbol.items()):
                for code, name in codebook.items():
                    merged.setdefault(code, name)
            for code, name_tuple in merged.items():
                key = (statement_type, code)
                old_zh, old_en = unified_codebook.get(key, ("", ""))
                new_zh, new_en = name_tuple
                # Prefer current run non-empty values; fall back to existing.
                unified_codebook[key] = (
                    new_zh if new_zh else old_zh,
                    new_en if new_en else old_en,
                )

        _merge_codebook("income_statement", income_codebook_by_symbol)
        _merge_codebook("balance_sheet", balance_codebook_by_symbol)
        _merge_codebook("cash_flow", cashflow_codebook_by_symbol)

    codebook_path.parent.mkdir(parents=True, exist_ok=True)
    with codebook_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["statement_type", "account_code", "account_name_zh", "account_name_en"])
        for (statement_type, account_code), names in sorted(unified_codebook.items()):
            name_zh, name_en = names
            writer.writerow([statement_type, account_code, name_zh, name_en])
    print(f"[+] Saved {codebook_path}")


if __name__ == "__main__":
    main()
