# 定義欄位映射與型別

# 欄位重新命名 (中文 -> 英文)
COLUMN_MAP = {
    # --- 共同欄位 ---
    "證券代號": "symbol",
    "代號": "symbol",
    "股票代號": "symbol", # 新增
    "證券名稱": "name",
    "名稱": "name",
    "公司名稱": "name", # 新增
    
    # --- 每日收盤行情 (Daily Quotes) ---
    "成交股數": "volume",
    "成交筆數": "transactions",
    "成交金額": "value",
    "成交金額(元)": "value",
    "開盤價": "open",
    "開盤": "open",
    "最高價": "high",
    "最高": "high",
    "最低價": "low",
    "最低": "low",
    "收盤價": "close",
    "收盤": "close",
    "漲跌(+/-)": "direction", 
    "漲跌": "change_raw",
    "漲跌價差": "change",
    "最後買價": "bid",
    "最後賣價": "ask",
    "最後買量(千股)": "bid_volume",  # OTC format (in thousands)
    "最後賣量(千股)": "ask_volume",  # OTC format (in thousands)
    "最後揭示買價": "last_disclosed_bid",
    "最後揭示賣價": "last_disclosed_ask",
    "最後揭示買量": "last_disclosed_bid_volume",
    "最後揭示賣量": "last_disclosed_ask_volume",
    "次日漲停價": "next_day_upper_limit",
    "次日跌停價": "next_day_lower_limit",
    "本益比": "pe_ratio",
    "殖利率(%)": "dividend_yield",
    "股利年度": "dividend_year",
    "每股股利(註)": "dividend_per_share",
    "股價淨值比": "pb_ratio",
    "財報年/季": "report_period",
    "": "empty_column",  # 空列名（某些檔案有空列）
    "column_8": "empty_column_8",  # Pandas 生成的空列名
    "column_12": "empty_column_12",  # Pandas 生成的空列名
    "column_16": "empty_column_16",  # Pandas 生成的空列名
    "column_19": "empty_column_19",  # Pandas 生成的空列名
    
    # --- 三大法人 (Institutional Investors) ---
    # SII 欄位
    "外陸資買進股數(不含外資自營商)": "foreign_buy",
    "外陸資賣出股數(不含外資自營商)": "foreign_sell",
    "外陸資買賣超股數(不含外資自營商)": "foreign_net",
    "外資自營商買進股數": "foreign_dealer_buy",
    "外資自營商賣出股數": "foreign_dealer_sell",
    "外資自營商買賣超股數": "foreign_dealer_net",
    "投信買進股數": "trust_buy",
    "投信賣出股數": "trust_sell",
    "投信買賣超股數": "trust_net",
    "自營商買賣超股數": "dealer_net",
    "自營商買進股數(自行買賣)": "dealer_self_buy",
    "自營商賣出股數(自行買賣)": "dealer_self_sell",
    "自營商買賣超股數(自行買賣)": "dealer_self_net",
    "自營商買進股數(避險)": "dealer_hedge_buy",
    "自營商賣出股數(避險)": "dealer_hedge_sell",
    "自營商買賣超股數(避險)": "dealer_hedge_net",
    "三大法人買賣超股數": "total_net",
    
    # OTC 欄位 (名稱略有不同)
    "外資及陸資(不含外資自營商)-買進股數": "foreign_buy",
    "外資及陸資(不含外資自營商)-賣出股數": "foreign_sell",
    "外資及陸資(不含外資自營商)-買賣超股數": "foreign_net",
    "外資自營商-買進股數": "foreign_dealer_buy",
    "外資自營商-賣出股數": "foreign_dealer_sell",
    "外資自營商-買賣超股數": "foreign_dealer_net",
    "外資及陸資-買進股數": "foreign_total_buy", # OTC 有這個加總欄位
    "外資及陸資-賣出股數": "foreign_total_sell",
    "外資及陸資-買賣超股數": "foreign_total_net",
    "投信-買進股數": "trust_buy",
    "投信-賣出股數": "trust_sell",
    "投信-買賣超股數": "trust_net",
    "自營商(自行買賣)-買進股數": "dealer_self_buy",
    "自營商(自行買賣)-賣出股數": "dealer_self_sell",
    "自營商(自行買賣)-買賣超股數": "dealer_self_net",
    "自營商(避險)-買進股數": "dealer_hedge_buy",
    "自營商(避險)-賣出股數": "dealer_hedge_sell",
    "自營商(避險)-買賣超股數": "dealer_hedge_net",
    "自營商-買賣超股數": "dealer_net", # 修正：讓它直接對應到標準欄位
    "自營商-買進股數": "dealer_total_buy",
    "自營商-賣出股數": "dealer_total_sell",
    "三大法人買賣超股數合計": "total_net",

    # --- 融資融券 (Margin Trading) ---
    # 合併後的欄位名 (由 utils.py 處理)
    "融資-買進": "margin_long_buy",
    "融資-賣出": "margin_long_sell",
    "融資-現金償還": "margin_long_cash_repay",
    "融資-前日餘額": "margin_long_prev_balance",
    "融資-今日餘額": "margin_long_balance",
    "融資-次一營業日限額": "margin_long_limit",
    "融券-買進": "margin_short_buy",
    "融券-賣出": "margin_short_sell",
    "融券-現券償還": "margin_short_cash_repay",
    "融券-前日餘額": "margin_short_prev_balance",
    "融券-今日餘額": "margin_short_balance",
    "融券-次一營業日限額": "margin_short_limit",
    "融券-資券互抵": "offset_balance",
    
    # 融券借券 (margin_sbl) 合併後的欄位名
    "融券-前日餘額": "margin_short_prev_balance",
    "融券-賣出": "margin_short_sell",
    "融券-買進": "margin_short_buy",
    "融券-今日餘額": "margin_short_balance",
    "融券-現券": "margin_short_cash",
    "融券-註記": "margin_short_note",
    "融券-次一營業日限額": "margin_short_limit",
    "借券賣出-當日餘額": "sbl_balance",
    "借券賣出-當日還券": "sbl_repay",
    "借券賣出-當日賣出": "sbl_sell",
    "借券賣出-前日餘額": "sbl_prev_balance",
    "借券賣出-次一營業日限額": "sbl_limit",
    "借券賣出-次一營業日可限額": "sbl_available_limit",
    "借券賣出-當日調整": "sbl_adjustment",
    "借券賣出-備註": "sbl_note",
    "融券當日餘額": "margin_short_balance", # OTC SBL
    "融券賣出": "margin_short_sell", # OTC SBL
    "融券買進": "margin_short_buy", # OTC SBL
    "融券前日餘額": "margin_short_prev_balance", # OTC SBL
    "融券現券": "margin_short_cash", # OTC SBL
    "融券限額": "margin_short_limit", # OTC SBL
    "融券": "margin_short_category", # SBL 分類列
    "借券賣出": "sbl_category", # SBL 分類列
    "借券賣出當日賣出": "sbl_sell", # OTC SBL (無橫槓)
    "借券賣出當日還券": "sbl_repay", # OTC SBL
    "借券賣出當日餘額": "sbl_balance", # OTC SBL
    "借券賣出 當日餘額": "sbl_balance", # OTC SBL (含空格)
    "借券賣出前日餘額": "sbl_prev_balance", # OTC SBL
    "借券賣出限額": "sbl_limit", # OTC SBL
    "次一營業日可借券賣出限額": "sbl_available_limit", # OTC SBL
    "借券賣出當日調整數額": "sbl_adjustment_amount", # OTC SBL
    "備註": "note", # OTC SBL
    "股票代號": "symbol", # OTC SBL
    "股票名稱": "name", # OTC SBL
    
    # OTC 欄位 (簡稱)
    "前資餘額(張)": "margin_long_prev_balance", # 注意單位是張，SII是股，需要統一
    "資買": "margin_long_buy",
    "資賣": "margin_long_sell",
    "現償": "margin_long_cash_repay",
    "資餘額": "margin_long_balance",
    "資屬證金": "margin_long_finance_company",
    "資使用率(%)": "margin_long_utilization",
    "資限額": "margin_long_limit",
    "前券餘額(張)": "margin_short_prev_balance",
    "券賣": "margin_short_sell",
    "券買": "margin_short_buy",
    "券償": "margin_short_cash_repay",
    "券餘額": "margin_short_balance",
    "券屬證金": "margin_short_finance_company",
    "券使用率(%)": "margin_short_utilization",
    "券限額": "margin_short_limit",
    "資券相抵(張)": "offset_balance",

    # --- 外資持股 (Foreign Holding) ---
    "發行股數": "issued_shares",
    "外資及陸資尚可投資股數": "foreign_investable_shares",
    "全體外資及陸資持有股數": "foreign_held_shares",
    "外資及陸資尚可投資比率": "foreign_investable_ratio",
    "全體外資及陸資持股比率": "foreign_held_ratio",
    "外資及陸資共用法令投資上限比率": "foreign_legal_limit_ratio",
    "陸資法令投資上限比率": "mainland_legal_limit_ratio",
    "國際證券編碼": "isin_code",
    "與前日異動原因(註)": "change_reason_note",
    "最近一次上市公司申報外資及陸資持股異動日期": "sii_last_update_date",
    "最近一次上櫃公司申報外資持股異動日期": "otc_last_update_date",

    # --- 大盤指數 (Market Indices) ---
    "指數": "index_name",
    "報酬指數": "index_name",
    "收盤指數": "index_close",
    "收市指數": "index_close", # OTC
    "漲跌點數": "index_change_points",
    "漲跌": "change", # 通用漲跌（用於非指數）
    "漲跌幅度(%)": "index_change_pct",
    "大盤資訊連結": "index_info_link",
}

# 需要轉為數值的欄位
NUMERIC_COLS = [
    # Quotes
    "volume", "transactions", "value", 
    "open", "high", "low", "close", "change", 
    "bid", "ask", "pe_ratio",
    
    # Institutional
    "foreign_buy", "foreign_sell", "foreign_net",
    "foreign_dealer_buy", "foreign_dealer_sell", "foreign_dealer_net",
    "trust_buy", "trust_sell", "trust_net",
    "dealer_net", "dealer_self_buy", "dealer_self_sell", "dealer_self_net",
    "dealer_hedge_buy", "dealer_hedge_sell", "dealer_hedge_net",
    "total_net",
    "foreign_total_buy", "foreign_total_sell", "foreign_total_net",
    "dealer_total_buy", "dealer_total_sell", "dealer_total_net",

    # Margin
    "margin_long_buy", "margin_long_sell", "margin_long_cash_repay",
    "margin_long_prev_balance", "margin_long_balance", "margin_long_limit",
    "margin_long_utilization",
    "margin_short_buy", "margin_short_sell", "margin_short_cash_repay",
    "margin_short_prev_balance", "margin_short_balance", "margin_short_limit",
    "margin_short_utilization",
    "offset_balance",
    "sbl_prev_balance", "sbl_sell", "sbl_repay", "sbl_balance",

    # Foreign Holding
    "issued_shares", "foreign_investable_shares", "foreign_held_shares",
    "foreign_investable_ratio", "foreign_held_ratio", "foreign_legal_limit_ratio"
]

# 標準化 Schema 定義 (確保 SII 與 OTC 欄位一致)
SCHEMA_COLS = {
    "daily_quotes": [
        "date", "market", "symbol", "name", 
        "open", "high", "low", "close", "volume", "value", 
        "transactions", "change", "direction", "bid", "ask", "pe_ratio",
        "src_file", "src_row", "src_col"
    ],
    "institutional_investors": [
        "date", "market", "symbol", "name",
        "foreign_buy", "foreign_sell", "foreign_net",
        "foreign_dealer_buy", "foreign_dealer_sell", "foreign_dealer_net",
        "trust_buy", "trust_sell", "trust_net",
        "dealer_self_buy", "dealer_self_sell", "dealer_self_net",
        "dealer_hedge_buy", "dealer_hedge_sell", "dealer_hedge_net",
        "dealer_net", "total_net",
        "src_file", "src_row", "src_col"
    ],
    "foreign_holding": [
        "date", "market", "symbol", "name",
        "issued_shares", "foreign_investable_shares", "foreign_held_shares",
        "foreign_investable_ratio", "foreign_held_ratio", "foreign_legal_limit_ratio",
        "src_file", "src_row", "src_col"
    ],
    "margin_trading": [
        "date", "market", "symbol", "name",
        "margin_long_buy", "margin_long_sell", "margin_long_cash_repay",
        "margin_long_prev_balance", "margin_long_balance", "margin_long_limit",
        "margin_short_buy", "margin_short_sell", "margin_short_cash_repay",
        "margin_short_prev_balance", "margin_short_balance", "margin_short_limit",
        "offset_balance",
        "src_file", "src_row", "src_col"
    ],
    "margin_sbl": [
        "date", "market", "symbol", "name",
        "margin_short_prev_balance", "margin_short_balance",
        "margin_short_buy", "margin_short_sell",
        "sbl_prev_balance", "sbl_sell", "sbl_repay", "sbl_balance",
        "src_file", "src_row", "src_col"
    ],
    "pe_ratio": [
        "date", "market", "symbol", "name",
        "pe_ratio",
        "src_file", "src_row", "src_col"
    ],
    "market_indices": [
        "date", "market", "symbol", "index_name", "index_close", "index_change_points",
        "src_file", "src_row", "src_col"
    ],
    "shareholding": [
        "date", "symbol", "level", "level_name", "holders", "shares", "percentage",
        "src_file", "src_row", "src_col"
    ],
    "income_statement": [
        "date", "market", "symbol", "name", "statement_type",
        "revenue", "cost_of_revenue", "gross_profit", "operating_expense",
        "operating_income", "non_operating_income", "pretax_income", "tax_expense",
        "net_income", "other_comprehensive_income", "comprehensive_income", "eps",
        "net_interest_income", "non_interest_income", "net_revenue", "other_income_net",
        "src_file", "src_row", "src_col"
    ],
    "balance_sheet": [
        "date", "market", "symbol", "name", "statement_type",
        "current_assets", "noncurrent_assets", "total_assets",
        "current_liabilities", "noncurrent_liabilities", "total_liabilities",
        "total_equity", "equity_parent",
        "share_capital", "capital_surplus", "retained_earnings",
        "other_equity", "treasury_shares", "nav_per_share",
        "src_file", "src_row", "src_col"
    ],
    "cash_flow": [
        "date", "market", "symbol", "name", "statement_type",
        "cash_flow_operating", "cash_flow_investing", "cash_flow_financing",
        "fx_effect", "net_cash_change", "cash_begin", "cash_end",
        "src_file", "src_row", "src_col"
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
        "src_file", "src_row", "src_col"
    ],
    "stock_info": [
        "symbol", "name", "industry", "market", "listing_date",
        "src_file", "src_row", "src_col"
    ],
    "stock_tags": [
        "symbol", "tag",
        "src_file", "src_row", "src_col"
    ]
}
