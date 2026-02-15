import polars as pl

# 標準化 Schema 欄位清單 (從原 processor/schemas.py 搬移並整理)
SCHEMA_COLS = {
    "daily_quotes": [
        "date", "market", "symbol", "name", 
        "open", "high", "low", "close", "volume", "value", 
        "transactions", "change", "direction", "bid", "ask",
        "pced_file", "pced_row", "pced_col"
    ],
    "institutional_investors": [
        "date", "market", "symbol", "name",
        "foreign_buy", "foreign_sell", "foreign_net",
        "foreign_dealer_buy", "foreign_dealer_sell", "foreign_dealer_net",
        "trust_buy", "trust_sell", "trust_net",
        "dealer_self_buy", "dealer_self_sell", "dealer_self_net",
        "dealer_hedge_buy", "dealer_hedge_sell", "dealer_hedge_net",
        "dealer_net", "total_net",
        "pced_file", "pced_row", "pced_col"
    ],
    "foreign_holding": [
        "date", "market", "symbol", "name",
        "issued_shares", "foreign_investable_shares", "foreign_held_shares",
        "foreign_investable_ratio", "foreign_held_ratio", "foreign_legal_limit_ratio",
        "pced_file", "pced_row", "pced_col"
    ],
    "margin_trading": [
        "date", "market", "symbol", "name",
        "margin_long_buy", "margin_long_sell", "margin_long_cash_repay",
        "margin_long_prev_balance", "margin_long_balance", "margin_long_limit",
        "margin_short_buy", "margin_short_sell", "margin_short_cash_repay",
        "margin_short_prev_balance", "margin_short_balance", "margin_short_limit",
        "offset_balance",
        "pced_file", "pced_row", "pced_col"
    ],
    "margin_sbl": [
        "date", "market", "symbol", "name",
        "margin_short_prev_balance", "margin_short_balance",
        "margin_short_buy", "margin_short_sell",
        "sbl_prev_balance", "sbl_sell", "sbl_repay", "sbl_balance",
        "pced_file", "pced_row", "pced_col"
    ],
    "pe_ratio": [
        "date", "market", "symbol", "name",
        "pe_ratio",
        "pced_file", "pced_row", "pced_col"
    ],
    "market_indices": [
        "date", "market", "symbol", "index_name", "index_close", "index_change_points",
        "pced_file", "pced_row", "pced_col"
    ],
    "shareholding": [
        "date", "symbol", "level", "level_name", "holders", "shares", "percentage",
        "pced_file", "pced_row", "pced_col"
    ],
    "monthly_revenue": [
        "date", "market", "symbol", "name", "revenue_current", "revenue_last_month",
        "revenue_last_year", "mom_pct", "yoy_pct", "revenue_cumulative",
        "revenue_cumulative_last_year", "cumulative_yoy_pct", "comment",
        "pced_file", "pced_row", "pced_col"
    ],
    "income_statement": [
        "date", "market", "symbol", "name", "statement_type",
        "revenue", "cost_of_revenue", "gross_profit", "operating_expense",
        "operating_income", "non_operating_income", "pretax_income", "tax_expense",
        "net_income", "other_comprehensive_income", "comprehensive_income", "eps",
        "net_interest_income", "non_interest_income", "net_revenue", "other_income_net",
        "pced_file", "pced_row", "pced_col"
    ],
    "balance_sheet": [
        "date", "market", "symbol", "name", "statement_type",
        "current_assets", "noncurrent_assets", "total_assets",
        "current_liabilities", "noncurrent_liabilities", "total_liabilities",
        "total_equity", "equity_parent",
        "share_capital", "capital_surplus", "retained_earnings",
        "other_equity", "treasury_shares", "nav_per_share",
        "pced_file", "pced_row", "pced_col"
    ],
    "cash_flow": [
        "date", "market", "symbol", "name", "statement_type",
        "cash_flow_operating", "cash_flow_investing", "cash_flow_financing",
        "fx_effect", "net_cash_change", "cash_begin", "cash_end",
        "pced_file", "pced_row", "pced_col"
    ],
    "quarterly_reports": [
        "date", "symbol", "name", "market",
        "revenue", "revenue_ly", "revenue_yoy",
        "op_income", "op_income_ly", "op_income_yoy",
        "non_op_income", "non_op_income_ly", "non_op_income_yoy",
        "pretax_income", "pretax_income_ly", "pretax_income_yoy",
        "net_income", "net_income_ly", "net_income_yoy",
        "eps", "eps_ly", "eps_yoy",
        "capital", "nav_per_share", "equity_to_assets_ratio",
        "current_ratio", "quick_ratio",
        "pced_file", "pced_row", "pced_col"
    ],
    "stock_info": [
        "symbol", "name", "industry", "market", "listing_date",
        "pced_file", "pced_row", "pced_col"
    ],
    "stock_tags": [
        "symbol", "tag",
        "pced_file", "pced_row", "pced_col"
    ]
}

# 全域欄位型別規則 (Explicit Types)
COLUMN_TYPES = {
    "symbol": pl.Utf8,
    "date": pl.Utf8,
    "market": pl.Utf8,
    "name": pl.Utf8,
    "industry": pl.Utf8,
    "listing_date": pl.Utf8,
    "tag": pl.Utf8,
    "direction": pl.Utf8,
    "bid": pl.Utf8,
    "ask": pl.Utf8,
    "level_name": pl.Utf8,
    "statement_type": pl.Utf8,
    "index_name": pl.Utf8,
    "comment": pl.Utf8,
    "pced_file": pl.Utf8,
    "pced_col": pl.Utf8,
    "pced_row": pl.Int64,
    "level": pl.Int64,
}

# 預設所有未在 COLUMN_TYPES 中定義的欄位為 Float64
DEFAULT_NUMERIC_TYPE = pl.Float64

def get_polars_schema(category):
    """根據類別產生 Polars 的 schema 定義"""
    if category not in SCHEMA_COLS:
        return None
    
    cols = SCHEMA_COLS[category]
    schema = {}
    for col in cols:
        schema[col] = COLUMN_TYPES.get(col, DEFAULT_NUMERIC_TYPE)
    return schema
