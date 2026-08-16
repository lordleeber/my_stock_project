#!/usr/bin/env python3
import argparse
import csv
import html
import re
from pathlib import Path


REVENUE_CODE = "4000"
OP_INCOME_CODE = "6900"
NON_OP_INCOME_CODE = "7000"
PRETAX_CODE = "7900"
EPS_CODE = "9750"
CAPITAL_CODE = "3110"

# 淨利的科目編號隨報表別而異，不是同一個數字的兩種寫法：
#   合併財報 8610 = 淨利歸屬於母公司業主（已扣除非控制權益；比 8200 更貼近舊版
#                   quarterly_reports 的口徑，這是當初選 8610 的理由）
#   個體財報 8200 = 本期淨利（淨損）
# 個體財報**沒有** 8610 —— 拿得到免編合併財報豁免的公司已無實質子公司，沒有非
# 控制權益可拆分，8200 本身即等同合併基礎下的 8610（issue.txt 用 4 檔轉換戶的
# 前期比較數對照 DB 舊合併數，逐項一致）。
# 舊版把科目寫死成 8610，個體財報進來時 net_income_q / net_income_acc 會整批
# 落成 NULL；2026-08-16 實測非金融 165 檔只有個體財報，約佔選股宇宙 10%。
NET_INCOME_CODE_CONSOLIDATED = "8610"
NET_INCOME_CODE_INDIVIDUAL = "8200"

REPORT_CATEGORY_CONSOLIDATED = "consolidated"
REPORT_CATEGORY_INDIVIDUAL = "individual"

# 取數依報表別查表決定，不用「8610 取不到就退 8200」的隱式推論。隱式版本同樣能
# 補起 NULL，但判別藏在取數邏輯裡，入庫後看不出哪一列是哪種基礎；report_category
# 一起寫進 quarterly_reports_xbrl，strategies 日後要分開處理才有依據。
NET_INCOME_CODE_BY_REPORT_CATEGORY = {
    REPORT_CATEGORY_CONSOLIDATED: NET_INCOME_CODE_CONSOLIDATED,
    REPORT_CATEGORY_INDIVIDUAL: NET_INCOME_CODE_INDIVIDUAL,
}

TOTAL_EQUITY_CODE = "3XXX"
TOTAL_ASSETS_CODE = "1XXX"
CURRENT_ASSETS_CODE = "11XX"
CURRENT_LIAB_CODE = "21XX"
INVENTORY_CODE = "130X"
PREPAID_EXPENSE_CODES = (
    "1280",  # Prepayments
    "1410",  # Prepayments
    "1411",  # Advance wages and salaries
    "1412",  # Prepaid rents
    "1414",  # Prepaid insurance premiums
    "1419",  # Other prepaid expenses
    "1421",  # Prepayments to suppliers
)

COMPANY_RE = re.compile(
    r"<ix:nonNumeric\b[^>]*\bname=['\"]tifrs-notes:CompanyChineseName['\"][^>]*>(.*?)</ix:nonNumeric>",
    re.IGNORECASE | re.DOTALL,
)
MARKET_RE = re.compile(
    r"<ix:nonNumeric\b[^>]*\bname=['\"]tifrs-notes:Market['\"][^>]*>(.*?)</ix:nonNumeric>",
    re.IGNORECASE | re.DOTALL,
)
# 值只有 "Consolidated report" / "Individual report" 兩種（41,000 份 raw 全數實測，
# 無缺漏、無第三種值）。DOTALL 是必要的：2021Q2_1519 這種檔案的值被斷行成
# "Consolidated \r\nreport"，靠 clean_value_text() 收斂空白才還原得回來。
REPORT_CATEGORY_RE = re.compile(
    r"<ix:nonNumeric\b[^>]*\bname=['\"]tifrs-notes:ReportCategory['\"][^>]*>(.*?)</ix:nonNumeric>",
    re.IGNORECASE | re.DOTALL,
)

OUTPUT_COLUMNS = [
    "date",
    "symbol",
    "market",
    "report_category",
    "revenue_q",
    "revenue_acc",
    "revenue_acc_ly",
    "revenue_acc_yoy",
    "op_income_q",
    "op_income_acc",
    "op_income_acc_ly",
    "op_income_acc_yoy",
    "non_op_income_q",
    "non_op_income_acc",
    "non_op_income_acc_ly",
    "non_op_income_acc_yoy",
    "pretax_income_q",
    "pretax_income_acc",
    "pretax_income_acc_ly",
    "pretax_income_acc_yoy",
    "net_income_q",
    "net_income_acc",
    "net_income_acc_ly",
    "net_income_acc_yoy",
    "eps_q",
    "eps_acc",
    "eps_acc_ly",
    "eps_acc_yoy",
    "capital",
    "nav_per_share",
    "equity_to_assets_ratio",
    "current_ratio",
    "quick_ratio",
    "publish_time",
    "period",
]

LY_YOY_COLUMNS = [
    "revenue_acc_ly",
    "revenue_acc_yoy",
    "op_income_acc_ly",
    "op_income_acc_yoy",
    "non_op_income_acc_ly",
    "non_op_income_acc_yoy",
    "pretax_income_acc_ly",
    "pretax_income_acc_yoy",
    "net_income_acc_ly",
    "net_income_acc_yoy",
    "eps_acc_ly",
    "eps_acc_yoy",
]

BACKFILL_QUARTERS = {"2020Q1", "2020Q2", "2020Q3", "2020Q4"}


class MissingPublishTimeSuffixError(ValueError):
    pass


class UnknownReportCategoryError(ValueError):
    """ReportCategory 缺漏或出現第三種值時拋出，不猜報表別。

    41,000 份 raw 全數帶得出這個欄位、值只有兩種，所以判不出來代表來源格式變了。
    這時退成合併基礎會把個體財報的 net_income 悄悄寫成 NULL —— 正是這支程式要修
    的那個 bug —— 所以照 processor 既有慣例 fail fast（見 processor/CLAUDE.md
    的 raw filename 規則），讓整季停下來被人看見。
    """


def to_float(text: str | None) -> float | None:
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0.0):
        return None
    return numerator / denominator


def calc_yoy(current: float | None, last_year: float | None) -> float | None:
    if current is None or last_year in (None, 0.0):
        return None
    return round((current - last_year) / abs(last_year) * 100.0, 2)


def calc_nav_per_share(
    total_equity: float | None, capital: float | None
) -> float | None:
    # Temporary approximation: shares_outstanding ~= capital / 10 (par value 10).
    if total_equity is None or capital in (None, 0.0):
        return None
    shares = capital / 10.0
    if shares == 0:
        return None
    return round(total_equity / shares, 2)


def period_text_quarter(quarter: str) -> str:
    year = int(quarter[:4])
    q = int(quarter[-1])
    if q == 1:
        return f"{year}0101-{year}0331"
    if q == 2:
        return f"{year}0401-{year}0630"
    if q == 3:
        return f"{year}0701-{year}0930"
    return f"{year}1001-{year}1231"


def period_text_accumulated(quarter: str) -> str:
    year = int(quarter[:4])
    q = int(quarter[-1])
    if q == 1:
        end = "0331"
    elif q == 2:
        end = "0630"
    elif q == 3:
        end = "0930"
    else:
        end = "1231"
    return f"{year}0101-{year}{end}"


def read_wide_code_map(path: Path, symbol: str) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("symbol") or "").strip() != symbol:
                continue
            code_map: dict[str, str] = {}
            for k, code in row.items():
                if not k.startswith("code"):
                    continue
                if not code:
                    continue
                idx = k[4:]
                val = row.get(f"value{idx}", "")
                code_map[code] = val
            return code_map
    raise ValueError(f"symbol={symbol} not found in {path}")


def decode_html(raw: bytes) -> str:
    for enc in ("utf-8", "utf-8-sig", "cp950", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def clean_value_text(raw_value: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw_value)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def resolve_raw_html_with_publish_time(
    raw_dir: Path, quarter: str, symbol: str
) -> tuple[Path, str]:
    quarter_dir = raw_dir / quarter[:4] / quarter
    if not quarter_dir.exists():
        raise FileNotFoundError(f"raw quarter dir not found: {quarter_dir}")

    dated_pattern = re.compile(
        rf"^{re.escape(quarter)}_{re.escape(symbol)}_(\d{{8}})\.html$"
    )
    legacy_pattern = re.compile(rf"^{re.escape(quarter)}_{re.escape(symbol)}\.html$")

    dated_matches: list[tuple[str, Path]] = []
    has_legacy = False
    for p in quarter_dir.glob(f"{quarter}_{symbol}*.html"):
        name = p.name
        m_dated = dated_pattern.match(name)
        if m_dated:
            dated_matches.append((m_dated.group(1), p))
            continue
        if legacy_pattern.match(name):
            has_legacy = True

    if not dated_matches:
        if has_legacy:
            raise MissingPublishTimeSuffixError(
                f"raw xbrl file missing _YYYYMMDD suffix for {quarter} {symbol}; "
                f"please rename {quarter}_{symbol}.html to {quarter}_{symbol}_YYYYMMDD.html"
            )
        raise FileNotFoundError(f"raw xbrl html not found for {quarter} {symbol}")

    publish_time, html_path = max(dated_matches, key=lambda x: x[0])
    return html_path, publish_time


def extract_meta_from_raw_html(html_path: Path) -> tuple[str, str, str]:
    """回傳 (公司中文名, market 原文, ReportCategory 原文)。三者都只讀一次檔案。"""
    text = decode_html(html_path.read_bytes())
    name_m = COMPANY_RE.search(text)
    market_m = MARKET_RE.search(text)
    category_m = REPORT_CATEGORY_RE.search(text)
    name = clean_value_text(name_m.group(1)) if name_m else ""
    market = clean_value_text(market_m.group(1)) if market_m else ""
    report_category = clean_value_text(category_m.group(1)) if category_m else ""
    return name, market, report_category


def normalize_market(raw_market: str) -> str:
    s = (raw_market or "").strip().lower()
    if "listed" in s:
        return "sii"
    if "otc" in s or "over-the-counter" in s:
        return "otc"
    return s


def normalize_report_category(raw_category: str) -> str:
    # 個體要先判。"Non-consolidated report" 是個體財報的另一種標準英譯，它**含有**
    # "consolidated" 子字串 —— 先比對合併會把它歸成合併基礎，於是去取 8610、取不到、
    # net_income 落成 NULL，而且因為分類「成功」了，UnknownReportCategoryError 不會
    # 觸發，正好對這批本 PR 要救的公司靜默失敗。
    # （目前 41,000 份 raw 只出現 Consolidated report / Individual report 兩種值，
    #   這裡純粹是為了讓誤判的方向倒向「停下來」而不是「猜成合併」。）
    s = (raw_category or "").strip().lower()
    if "individual" in s or "non-consolidated" in s or "nonconsolidated" in s:
        return REPORT_CATEGORY_INDIVIDUAL
    if "consolidated" in s:
        return REPORT_CATEGORY_CONSOLIDATED
    return ""


def build_experiment_row(
    processed_dir: Path, raw_dir: Path, quarter: str, symbol: str
) -> dict[str, str | float | None]:
    year = quarter[:4]
    q_num = int(quarter[-1])
    inc_q_path = (
        processed_dir / "income_statement_xbrl" / year / quarter / "all_quarter.csv"
    )
    inc_a_path = (
        processed_dir / "income_statement_xbrl" / year / quarter / "all_accumulated.csv"
    )
    bs_path = processed_dir / "balance_sheet_xbrl" / year / quarter / "all.csv"
    cf_path = processed_dir / "cash_flow_xbrl" / year / quarter / "all_accumulated.csv"

    inc_q = read_wide_code_map(inc_q_path, symbol)
    inc_a = read_wide_code_map(inc_a_path, symbol)
    bs = read_wide_code_map(bs_path, symbol)
    _cf = read_wide_code_map(cf_path, symbol)  # keep dependency explicit

    prev_year_quarter = f"{int(year) - 1}Q{q_num}"
    prev_year = prev_year_quarter[:4]
    prev_inc_a_path = (
        processed_dir
        / "income_statement_xbrl"
        / prev_year
        / prev_year_quarter
        / "all_accumulated.csv"
    )
    prev_inc_a: dict[str, str] = {}
    if prev_inc_a_path.exists():
        try:
            # BUG（既存，本 PR 不動）：read_wide_code_map() 回傳的是 dict，這裡卻拿
            # 它解包成兩個變數。實務上損益表寬列的科目數不會剛好是 2，所以解包幾乎
            # 總是拋 ValueError 被下面接掉，prev_inc_a 留在 {} —— 實測 12 個
            # *_acc_ly / *_acc_yoy 欄位在全部 26 季 100% NULL。
            # 另外兩條路徑也落到同一個 except：symbol 不在去年同季檔案裡時，
            # read_wide_code_map() 自己就拋 ValueError。而萬一科目剛好 2 個，解包會
            # 「成功」讓 prev_inc_a 變成一個科目字串，之後 .get() 拋 AttributeError
            # —— 那個不會被這裡接到，整檔會被 main() 的廣義 handler 丟出該季。
            # 其中 eps_acc_yoy / revenue_acc_yoy 還被 strategies/step1_prepare_data.py
            # 當特徵吃進去。修它會動到 ML 特徵、必須連帶重跑 4/4 的驗證，所以留給
            # 獨立的 PR；詳見 KNOWN_ISSUES.md。
            prev_inc_a, _ = read_wide_code_map(prev_inc_a_path, symbol)
        except ValueError:
            prev_inc_a = {}

    raw_html_path, publish_time = resolve_raw_html_with_publish_time(
        raw_dir, quarter, symbol
    )
    name, market, raw_report_category = extract_meta_from_raw_html(raw_html_path)
    report_category = normalize_report_category(raw_report_category)
    net_income_code = NET_INCOME_CODE_BY_REPORT_CATEGORY.get(report_category)
    if net_income_code is None:
        raise UnknownReportCategoryError(
            f"unrecognized tifrs-notes:ReportCategory in {raw_html_path}: "
            f"{raw_report_category!r} "
            "(expected 'Consolidated report' or 'Individual report')"
        )

    total_equity = to_float(bs.get(TOTAL_EQUITY_CODE))
    total_assets = to_float(bs.get(TOTAL_ASSETS_CODE))
    current_assets = to_float(bs.get(CURRENT_ASSETS_CODE))
    current_liab = to_float(bs.get(CURRENT_LIAB_CODE))
    inventory = to_float(bs.get(INVENTORY_CODE))
    prepaid_expense_total = 0.0
    prepaid_expense_found = False
    for code in PREPAID_EXPENSE_CODES:
        val = to_float(bs.get(code))
        if val is None:
            continue
        prepaid_expense_total += val
        prepaid_expense_found = True

    equity_to_assets_ratio = safe_div(total_equity, total_assets)
    if equity_to_assets_ratio is not None:
        equity_to_assets_ratio *= 100.0

    current_ratio = safe_div(current_assets, current_liab)
    quick_assets = None
    if current_assets is not None and inventory is not None:
        quick_assets = current_assets - inventory
        if prepaid_expense_found:
            quick_assets -= prepaid_expense_total
    quick_ratio = safe_div(
        quick_assets,
        current_liab,
    )

    row: dict[str, str | float | None] = {k: None for k in OUTPUT_COLUMNS}
    row["date"] = quarter
    row["symbol"] = symbol
    row["market"] = normalize_market(market)
    row["report_category"] = report_category
    row["publish_time"] = publish_time

    row["revenue_q"] = to_float(inc_q.get(REVENUE_CODE))
    row["revenue_acc"] = to_float(inc_a.get(REVENUE_CODE))
    row["revenue_acc_ly"] = to_float(prev_inc_a.get(REVENUE_CODE))
    row["revenue_acc_yoy"] = calc_yoy(row["revenue_acc"], row["revenue_acc_ly"])
    row["op_income_q"] = to_float(inc_q.get(OP_INCOME_CODE))
    row["op_income_acc"] = to_float(inc_a.get(OP_INCOME_CODE))
    row["op_income_acc_ly"] = to_float(prev_inc_a.get(OP_INCOME_CODE))
    row["op_income_acc_yoy"] = calc_yoy(row["op_income_acc"], row["op_income_acc_ly"])
    row["non_op_income_q"] = to_float(inc_q.get(NON_OP_INCOME_CODE))
    row["non_op_income_acc"] = to_float(inc_a.get(NON_OP_INCOME_CODE))
    row["non_op_income_acc_ly"] = to_float(prev_inc_a.get(NON_OP_INCOME_CODE))
    row["non_op_income_acc_yoy"] = calc_yoy(
        row["non_op_income_acc"], row["non_op_income_acc_ly"]
    )
    row["pretax_income_q"] = to_float(inc_q.get(PRETAX_CODE))
    row["pretax_income_acc"] = to_float(inc_a.get(PRETAX_CODE))
    row["pretax_income_acc_ly"] = to_float(prev_inc_a.get(PRETAX_CODE))
    row["pretax_income_acc_yoy"] = calc_yoy(
        row["pretax_income_acc"], row["pretax_income_acc_ly"]
    )
    row["net_income_q"] = to_float(inc_q.get(net_income_code))
    row["net_income_acc"] = to_float(inc_a.get(net_income_code))
    # 注意：prev_inc_a 取的是去年同季，那一季的報表別未必與本季相同（轉換戶）。
    # 目前無妨 —— prev_inc_a 恆為空 dict，見 build_experiment_row 內的說明。
    row["net_income_acc_ly"] = to_float(prev_inc_a.get(net_income_code))
    row["net_income_acc_yoy"] = calc_yoy(
        row["net_income_acc"], row["net_income_acc_ly"]
    )
    row["eps_q"] = to_float(inc_q.get(EPS_CODE))
    row["eps_acc"] = to_float(inc_a.get(EPS_CODE))
    row["eps_acc_ly"] = to_float(prev_inc_a.get(EPS_CODE))
    row["eps_acc_yoy"] = calc_yoy(row["eps_acc"], row["eps_acc_ly"])
    row["capital"] = to_float(bs.get(CAPITAL_CODE))
    row["nav_per_share"] = calc_nav_per_share(total_equity, row["capital"])
    row["equity_to_assets_ratio"] = equity_to_assets_ratio
    row["current_ratio"] = current_ratio
    row["quick_ratio"] = quick_ratio
    return row


def write_output_csv(out_file: Path, rows: list[dict[str, str | float | None]]) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def list_symbols_from_raw(raw_dir: Path, quarter: str) -> list[str]:
    quarter_dir = raw_dir / quarter[:4] / quarter
    if not quarter_dir.exists():
        raise FileNotFoundError(f"raw quarter dir not found: {quarter_dir}")
    pattern = re.compile(rf"^{re.escape(quarter)}_(\d{{4}})(?:_\d{{8}})?\.html$")
    symbols: set[str] = set()
    for p in quarter_dir.glob(f"{quarter}_*.html"):
        m = pattern.match(p.name)
        if m:
            symbols.add(m.group(1))
    return sorted(symbols)


def backfill_ly_yoy_from_quarterly_reports(
    processed_dir: Path, quarter: str, target_files: list[Path]
) -> None:
    qr_path = processed_dir / "quarterly_reports" / quarter[:4] / quarter / "all.csv"
    if not qr_path.exists():
        print(f"[WARN] skip ly/yoy backfill: source not found {qr_path}")
        return

    qr_map: dict[str, dict[str, str]] = {}
    with qr_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            sym = (row.get("symbol") or "").strip()
            if sym:
                qr_map[sym] = row

    for path in target_files:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or OUTPUT_COLUMNS
            rows = list(reader)

        updates = 0
        for row in rows:
            sym = (row.get("symbol") or "").strip()
            src = qr_map.get(sym)
            if not src:
                continue
            for col in LY_YOY_COLUMNS:
                if (row.get(col) or "").strip() != "":
                    continue
                value = (src.get(col) or "").strip()
                if value == "":
                    continue
                row[col] = value
                updates += 1

        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        print(f"[backfill] {path} updates={updates} rows={len(rows)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build quarterly_reports_xbrl from XBRL wide CSVs."
    )
    parser.add_argument("--quarter", required=True, help="YYYYQX, e.g. 2020Q1")
    parser.add_argument("--symbol", help="single stock symbol, e.g. 2330")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--raw-dir", default="data/raw/xbrl")
    args = parser.parse_args()

    processed_dir = Path(args.processed_dir)
    raw_dir = Path(args.raw_dir)
    quarter = args.quarter.strip()
    out_dir = processed_dir / "quarterly_reports_xbrl" / quarter[:4] / quarter

    if args.symbol:
        symbols = [args.symbol.strip()]
    else:
        symbols = list_symbols_from_raw(raw_dir, quarter)

    rows_quarter: list[dict[str, str | float | None]] = []
    rows_acc: list[dict[str, str | float | None]] = []
    failed: list[tuple[str, str]] = []
    period_q = period_text_quarter(quarter)
    period_a = period_text_accumulated(quarter)

    for symbol in symbols:
        try:
            row = build_experiment_row(processed_dir, raw_dir, quarter, symbol)
            row_quarter = dict(row)
            row_quarter["period"] = period_q
            rows_quarter.append(row_quarter)

            row_acc = dict(row)
            row_acc["period"] = period_a
            rows_acc.append(row_acc)
        except (MissingPublishTimeSuffixError, UnknownReportCategoryError):
            raise
        except Exception as e:
            failed.append((symbol, str(e)))

    out_quarter = out_dir / "all_quarter.csv"
    out_acc = out_dir / "all_accumulated.csv"
    write_output_csv(out_quarter, rows_quarter)
    write_output_csv(out_acc, rows_acc)
    if quarter in BACKFILL_QUARTERS:
        backfill_ly_yoy_from_quarterly_reports(
            processed_dir, quarter, [out_quarter, out_acc]
        )
    else:
        print(f"[backfill] skipped for {quarter} (only enabled for 2020Q1~2020Q4)")

    print(f"Saved quarterly CSV: {out_quarter} (rows={len(rows_quarter)})")
    print(f"Saved accumulated CSV: {out_acc} (rows={len(rows_acc)})")
    if failed:
        print(f"[WARN] skipped symbols: {len(failed)}")
        for symbol, reason in failed[:20]:
            print(f"  - {symbol}: {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
