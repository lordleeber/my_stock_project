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
        "revenue_q", "revenue_acc",
        "cost_of_revenue_q", "cost_of_revenue_acc",
        "gross_profit_q", "gross_profit_acc",
        "operating_expense_q", "operating_expense_acc",
        "operating_income_q", "operating_income_acc",
        "non_operating_income_q", "non_operating_income_acc",
        "pretax_income_q", "pretax_income_acc",
        "tax_expense_q", "tax_expense_acc",
        "net_income_q", "net_income_acc",
        "other_comprehensive_income_q", "other_comprehensive_income_acc",
        "comprehensive_income_q", "comprehensive_income_acc",
        "eps_q", "eps_acc",
        "net_interest_income_q", "net_interest_income_acc",
        "non_interest_income_q", "non_interest_income_acc",
        "net_revenue_q", "net_revenue_acc",
        "other_income_net_q", "other_income_net_acc",
        "pced_file", "pced_row", "pced_col"
    ],
    "balance_sheet": [
        "date", "market", "symbol", "name", "statement_type",
        "current_assets", "noncurrent_assets", "total_assets",
        "current_liabilities", "noncurrent_liabilities", "total_liabilities",
        "total_equity", "equity_parent",
        "share_capital", "capital_surplus", "retained_earnings",
        "other_equity", "treasury_shares",
        "inventory", "accounts_receivable",
        "nav_per_share",
        "pced_file", "pced_row", "pced_col"
    ],
    "cash_flow": [
        "date", "market", "symbol", "name", "statement_type",
        "cash_flow_operating_q", "cash_flow_operating_acc",
        "cash_flow_investing_q", "cash_flow_investing_acc",
        "cash_flow_financing_q", "cash_flow_financing_acc",
        "fx_effect_q", "fx_effect_acc",
        "net_cash_change_q", "net_cash_change_acc",
        "cash_begin", "cash_end",
        "pced_file", "pced_row", "pced_col"
    ],
    "quarterly_reports": [
        "date", "symbol", "name", "market",
        "revenue_q", "revenue_acc", "revenue_acc_ly", "revenue_acc_yoy",
        "op_income_q", "op_income_acc", "op_income_acc_ly", "op_income_acc_yoy",
        "non_op_income_q", "non_op_income_acc", "non_op_income_acc_ly", "non_op_income_acc_yoy",
        "pretax_income_q", "pretax_income_acc", "pretax_income_acc_ly", "pretax_income_acc_yoy",
        "net_income_q", "net_income_acc", "net_income_acc_ly", "net_income_acc_yoy",
        "eps_q", "eps_acc", "eps_acc_ly", "eps_acc_yoy",
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
    ],
    "dividend": [
        "date", "symbol", "name", "close_before", "ref_price", "rights_dividend_value", "type",
        "pced_file", "pced_row", "pced_col"
    ],
    "valuation_analysis": [
        "date", "symbol", "close", "ttm_eps", "pe_ratio_calculated", "pe_ratio_from_pe_table", "pe_percentile",
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
    "type": pl.Utf8,
    "pe_percentile": pl.Float64,
    "ttm_eps": pl.Float64,
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
