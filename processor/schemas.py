import sys
import os
# 加入 common 目錄到搜尋路徑，以便在容器中引用
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.schemas import SCHEMA_COLS

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
    "最後買價": "last_bid",
    "最後賣價": "last_ask",
    "最後買量(千股)": "last_bid_volume",  # OTC format (in thousands)
    "最後賣量(千股)": "last_ask_volume",  # OTC format (in thousands)
    "最後買量(張數)": "last_bid_volume",  # OTC newer format
    "最後賣量(張數)": "last_ask_volume",  # OTC newer format
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
    "column_5": "empty_column_5",  # Pandas/Polars 生成的空列名（例如 pe_ratio SII 尾端空欄）
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

    # --- 除權除息 (Dividend) ---
    "資料日期": "date",
    "除權息前收盤價": "close_before",
    "除權息參考價": "ref_price",
    "權值+息值": "rights_dividend_value",
    "權/息": "type",
}

# 需要轉為數值的欄位
