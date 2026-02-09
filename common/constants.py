# API 設定
API_BASE = "http://100.103.191.79:8000"

# HTTP 請求設定
HTTP_TIMEOUT = 30  # 秒
HTTP_RETRIES = 3
HTTP_BACKOFF_FACTOR = 0.5

# 中英文類別對照表 (統一目錄命名)
CATEGORY_MAP = {
    "每日收盤行情": "daily_quotes",
    "三大法人買賣金額統計表": "institutional_summary",
    "三大法人買賣超日報": "institutional_investors",
    "外資及陸資投資持股統計": "foreign_holding",
    "融資融券": "margin_trading",
    "融券借券": "margin_sbl",
    "本益比殖利率淨值": "pe_ratio",
    "指數行情": "market_indices",
}
