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
NET_INCOME_CODE = "8610"  # Closer to quarterly_reports than 8200.
EPS_CODE = "9750"
CAPITAL_CODE = "3110"

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

OUTPUT_COLUMNS = [
    "date",
    "symbol",
    "market",
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


def calc_nav_per_share(total_equity: float | None, capital: float | None) -> float | None:
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


def resolve_raw_html_with_publish_time(raw_dir: Path, quarter: str, symbol: str) -> tuple[Path, str]:
    quarter_dir = raw_dir / quarter[:4] / quarter
    if not quarter_dir.exists():
        raise FileNotFoundError(f"raw quarter dir not found: {quarter_dir}")

    dated_pattern = re.compile(rf"^{re.escape(quarter)}_{re.escape(symbol)}_(\d{{8}})\.html$")
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


def extract_name_market_from_raw_html(html_path: Path) -> tuple[str, str]:
    text = decode_html(html_path.read_bytes())
    name_m = COMPANY_RE.search(text)
    market_m = MARKET_RE.search(text)
    name = clean_value_text(name_m.group(1)) if name_m else ""
    market = clean_value_text(market_m.group(1)) if market_m else ""
    return name, market


def normalize_market(raw_market: str) -> str:
    s = (raw_market or "").strip().lower()
    if "listed" in s:
        return "sii"
    if "otc" in s or "over-the-counter" in s:
        return "otc"
    return s


def build_experiment_row(processed_dir: Path, raw_dir: Path, quarter: str, symbol: str) -> dict[str, str | float | None]:
    year = quarter[:4]
    q_num = int(quarter[-1])
    inc_q_path = processed_dir / "income_statement_xbrl" / year / quarter / "all_quarter.csv"
    inc_a_path = processed_dir / "income_statement_xbrl" / year / quarter / "all_accumulated.csv"
    bs_path = processed_dir / "balance_sheet_xbrl" / year / quarter / "all.csv"
    cf_path = processed_dir / "cash_flow_xbrl" / year / quarter / "all_accumulated.csv"

    inc_q = read_wide_code_map(inc_q_path, symbol)
    inc_a = read_wide_code_map(inc_a_path, symbol)
    bs = read_wide_code_map(bs_path, symbol)
    _cf = read_wide_code_map(cf_path, symbol)  # keep dependency explicit

    prev_year_quarter = f"{int(year) - 1}Q{q_num}"
    prev_year = prev_year_quarter[:4]
    prev_inc_a_path = processed_dir / "income_statement_xbrl" / prev_year / prev_year_quarter / "all_accumulated.csv"
    prev_inc_a: dict[str, str] = {}
    if prev_inc_a_path.exists():
        try:
            prev_inc_a, _ = read_wide_code_map(prev_inc_a_path, symbol)
        except ValueError:
            prev_inc_a = {}

    raw_html_path, publish_time = resolve_raw_html_with_publish_time(raw_dir, quarter, symbol)
    name, market = extract_name_market_from_raw_html(raw_html_path)

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
    row["non_op_income_acc_yoy"] = calc_yoy(row["non_op_income_acc"], row["non_op_income_acc_ly"])
    row["pretax_income_q"] = to_float(inc_q.get(PRETAX_CODE))
    row["pretax_income_acc"] = to_float(inc_a.get(PRETAX_CODE))
    row["pretax_income_acc_ly"] = to_float(prev_inc_a.get(PRETAX_CODE))
    row["pretax_income_acc_yoy"] = calc_yoy(row["pretax_income_acc"], row["pretax_income_acc_ly"])
    row["net_income_q"] = to_float(inc_q.get(NET_INCOME_CODE))
    row["net_income_acc"] = to_float(inc_a.get(NET_INCOME_CODE))
    row["net_income_acc_ly"] = to_float(prev_inc_a.get(NET_INCOME_CODE))
    row["net_income_acc_yoy"] = calc_yoy(row["net_income_acc"], row["net_income_acc_ly"])
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


def backfill_ly_yoy_from_quarterly_reports(processed_dir: Path, quarter: str, target_files: list[Path]) -> None:
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
    parser = argparse.ArgumentParser(description="Build quarterly_reports_xbrl from XBRL wide CSVs.")
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
        except MissingPublishTimeSuffixError:
            raise
        except Exception as e:
            failed.append((symbol, str(e)))

    out_quarter = out_dir / "all_quarter.csv"
    out_acc = out_dir / "all_accumulated.csv"
    write_output_csv(out_quarter, rows_quarter)
    write_output_csv(out_acc, rows_acc)
    if quarter in BACKFILL_QUARTERS:
        backfill_ly_yoy_from_quarterly_reports(processed_dir, quarter, [out_quarter, out_acc])
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
