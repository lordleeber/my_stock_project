# 定義欄位映射與型別

# 欄位重新命名 (中文 -> 英文)
COLUMN_MAP = {
    # --- 共同欄位 ---
    "證券代號": "symbol",
    "代號": "symbol",
    "證券名稱": "name",
    "名稱": "name",
    
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
    "本益比": "pe_ratio",
    
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
    "自營商-買進股數": "dealer_total_buy",
    "自營商-賣出股數": "dealer_total_sell",
    "自營商-買賣超股數": "dealer_total_net",
    "三大法人買賣超股數合計": "total_net",

    # --- 融資融券 (Margin Trading) ---
    # SII 欄位
    "融資買進": "margin_long_buy",
    "融資賣出": "margin_long_sell",
    "融資現金償還": "margin_long_cash_repay",
    "融資前日餘額": "margin_long_prev_balance",
    "融資今日餘額": "margin_long_balance",
    "融資限額": "margin_long_limit",
    "融券買進": "margin_short_buy",
    "融券賣出": "margin_short_sell",
    "融券現券償還": "margin_short_cash_repay",
    "融券前日餘額": "margin_short_prev_balance",
    "融券今日餘額": "margin_short_balance",
    "融券限額": "margin_short_limit",
    "資券互抵": "offset_balance",
    
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

    # Foreign Holding
    "issued_shares", "foreign_investable_shares", "foreign_held_shares",
    "foreign_investable_ratio", "foreign_held_ratio", "foreign_legal_limit_ratio"
]