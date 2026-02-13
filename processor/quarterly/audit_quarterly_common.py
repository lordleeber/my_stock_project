import os
import polars as pl

PROCESSED_DIR = os.getenv("PROCESSED_DIR", "data/processed")

REQUIRED_FIELDS = {
    "income_statement": ["date", "market", "symbol", "name", "statement_type"],
    "balance_sheet": ["date", "market", "symbol", "name", "statement_type"],
    "cash_flow": ["date", "market", "symbol", "name", "statement_type"],
    "quarterly_reports": ["date", "market", "symbol", "name"],
}

NUMERIC_FIELDS = {
    "income_statement": [
        "revenue", "cost_of_revenue", "gross_profit", "operating_expense",
        "operating_income", "non_operating_income", "pretax_income", "tax_expense",
        "net_income", "other_comprehensive_income", "comprehensive_income", "eps",
        "net_interest_income", "non_interest_income", "net_revenue", "other_income_net",
    ],
    "balance_sheet": [
        "current_assets", "noncurrent_assets", "total_assets",
        "current_liabilities", "noncurrent_liabilities", "total_liabilities",
        "total_equity", "equity_parent",
        "share_capital", "capital_surplus", "retained_earnings",
        "other_equity", "treasury_shares", "nav_per_share",
    ],
    "cash_flow": [
        "cash_flow_operating", "cash_flow_investing", "cash_flow_financing",
        "fx_effect", "net_cash_change", "cash_begin", "cash_end",
    ],
    "quarterly_reports": [
        "revenue", "revenue_ly", "revenue_yoy",
        "op_income", "op_income_ly", "op_income_yoy",
        "non_op_income", "non_op_income_ly", "non_op_income_yoy",
        "pretax_income", "pretax_income_ly", "pretax_income_yoy",
        "net_income", "net_income_ly", "net_income_yoy",
        "eps", "eps_ly", "eps_yoy",
        "capital", "nav_per_share", "equity_to_assets_ratio",
        "current_ratio", "quick_ratio",
    ],
}


def is_quarter(s):
    return bool(s) and len(s) == 6 and "Q" in s and s[:4].isdigit() and s[5].isdigit()


def list_quarters(start_q, end_q):
    year = int(start_q[:4])
    q = int(start_q[5])
    end_year = int(end_q[:4])
    end_qn = int(end_q[5])
    quarters = []
    while (year, q) <= (end_year, end_qn):
        quarters.append(f"{year}Q{q}")
        q += 1
        if q > 4:
            year += 1
            q = 1
    return quarters


def load_csv(path):
    try:
        return pl.read_csv(path, infer_schema_length=0)
    except Exception:
        return None


def get_processed_csv_path(category, date_str):
    year = date_str[:4]
    return os.path.join(PROCESSED_DIR, category, year, date_str, "all.csv")


def check_category(category, date_str, issues):
    csv_path = get_processed_csv_path(category, date_str)
    if not os.path.exists(csv_path):
        issues.append(f"{category} {date_str}: missing processed file")
        return

    df = load_csv(csv_path)
    if df is None or df.is_empty():
        issues.append(f"{category} {date_str}: empty processed file")
        return

    for field in REQUIRED_FIELDS[category]:
        if field not in df.columns:
            issues.append(f"{category} {date_str}: missing column {field}")
            return

    for field in ["date", "market", "symbol", "name", "statement_type"]:
        if field in df.columns:
            if df.filter((pl.col(field).is_null()) | (pl.col(field) == "")).height > 0:
                issues.append(f"{category} {date_str}: null/empty {field}")
                break

    for field in NUMERIC_FIELDS[category]:
        if field in df.columns:
            dtype = df.schema.get(field)
            if dtype is None:
                continue
            if dtype in (
                pl.Float64, pl.Float32,
                pl.Int64, pl.Int32, pl.Int16, pl.Int8,
                pl.UInt64, pl.UInt32, pl.UInt16, pl.UInt8,
            ):
                if df.select(pl.col(field).is_not_null() & ~pl.col(field).is_finite()).to_series().any():
                    issues.append(f"{category} {date_str}: non-finite {field}")
                    break

