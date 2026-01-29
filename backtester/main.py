import os
import sys
import pandas as pd
from sqlalchemy import create_engine, text

# 讓 Python 能找到 strategy 模組
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy.core import run_backtest, StrategyConfig

def get_db_url():
    user = os.getenv("DB_USER") or "user"
    password = os.getenv("DB_PASSWORD") or "password"
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def format_date(date_str):
    """將 YYYYMMDD 或 YYYY-MM-DD 格式轉換為 YYYY-MM-DD"""
    if not date_str:
        return None
    date_str = date_str.strip()
    if len(date_str) == 8 and date_str.isdigit():
        # YYYYMMDD -> YYYY-MM-DD
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str

def fetch_data(engine, start_date, end_date):
    # 為了確保 T+N 有資料，我們往後多抓 60 天
    query_end_dt = pd.to_datetime(end_date) + pd.Timedelta(days=60)
    query_end = query_end_dt.strftime("%Y-%m-%d")
    
    print(f"Fetching data for Backtest ({start_date} ~ {query_end})...")
    query = text("""
        SELECT t.date, t.symbol, d.name, d.open, d.close, d.volume, t.vma10
        FROM technical_indicators t
        JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
        WHERE t.date >= :start AND t.date <= :end
        ORDER BY t.symbol, t.date
    """)
    df = pd.read_sql(query, engine, params={"start": start_date, "end": query_end})
    if df.empty:
        print("No data found.")
        return None
    
    df['date'] = pd.to_datetime(df['date'])
    return df

def main():
    print("Starting Backtester CLI...")
    db_url = get_db_url()
    engine = create_engine(db_url)

    # 環境變數設定
    start_date_raw = os.getenv("START_DATE", "2025-05-01")
    end_date_raw = os.getenv("END_DATE", "2025-05-31")
    start_date = format_date(start_date_raw) or "2025-05-01"
    end_date = format_date(end_date_raw) or "2025-05-31"

    hold_days = int(os.getenv("HOLD_DAYS", "3"))
    allow_pyramiding = os.getenv("ALLOW_PYRAMIDING", "true").lower() == "true"
    only_red_candle = os.getenv("ONLY_RED_CANDLE", "false").lower() == "true"

    # 停損停利 (預設 0.0 表示不啟用)
    take_profit_env = os.getenv("TAKE_PROFIT_PCT", "0.0")
    stop_loss_env = os.getenv("STOP_LOSS_PCT", "0.0")

    take_profit_pct = float(take_profit_env)
    stop_loss_pct = float(stop_loss_env)

    # 輸出參數設定
    print("\n" + "="*50)
    print("BACKTEST PARAMETERS")
    print("="*50)
    print(f"Period         : {start_date} ~ {end_date}")
    print(f"Hold Days      : {hold_days}")
    print(f"Red Candle Only: {only_red_candle}")
    print(f"Pyramiding     : {allow_pyramiding}")
    print(f"Take Profit    : {take_profit_pct*100:.1f}%" if take_profit_pct > 0 else "Take Profit    : Disabled")
    print(f"Stop Loss      : {stop_loss_pct*100:.1f}%" if stop_loss_pct > 0 else "Stop Loss      : Disabled")
    print("="*50 + "\n")
    
    df = fetch_data(engine, start_date, end_date)
    if df is None: return

    # 設定策略參數
    config = StrategyConfig(
        strategy_mode='shares', # CLI 預設用 shares 方便比較
        fixed_shares=1000,
        hold_days=hold_days,
        allow_pyramiding=allow_pyramiding,
        only_red_candle=only_red_candle,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct
    )
    
    # 執行回測
    result = run_backtest(df, config)
    summary = result['summary']
    trades = result['trades'] # List[TradeRecord]
    
    # 輸出報告
    print("\n" + "="*60)
    print(f"BACKTEST RESULTS")
    print("="*60)
    print(f"Strategy       : Volume Breakout (5x VMA10)")
    print(f"Fixed Shares   : 1,000 shares per trade")
    print(f"Period         : {start_date} ~ {end_date}")
    print("-" * 60)
    print(f"Total Trades   : {summary.total_trades}")
    print(f"Win Rate       : {summary.win_rate:.2f}%")
    print(f"Total Profit   : NT$ {summary.total_profit:,.0f}")
    print(f"Total Cost     : NT$ {summary.total_cost:,.0f}")
    print(f"Total ROI      : {summary.roi:.2f}%")
    print(f"Avg Profit/Trade: NT$ {summary.total_profit/summary.total_trades:,.0f}" if summary.total_trades > 0 else "Avg Profit/Trade: N/A")
    print("="*60)
    
    if trades:
        df_trades = pd.DataFrame([t.__dict__ for t in trades])
        print("Top 3 Profitable Trades:")
        print(df_trades.sort_values('profit', ascending=False).head(3)[['symbol', 'name', 'buy_date', 'profit']].to_string(index=False))
        print("-" * 50)
        print("Top 3 Loss Trades:")
        print(df_trades.sort_values('profit', ascending=True).head(3)[['symbol', 'name', 'buy_date', 'profit']].to_string(index=False))

if __name__ == "__main__":
    main()
