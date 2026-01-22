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
    start_date = os.getenv("START_DATE", "2025-05-01")
    end_date = os.getenv("END_DATE", "2025-05-31")
    hold_days = int(os.getenv("HOLD_DAYS", "3"))
    allow_pyramiding = os.getenv("ALLOW_PYRAMIDING", "true").lower() == "true"
    only_red_candle = os.getenv("ONLY_RED_CANDLE", "false").lower() == "true"
    
    # 停損停利 (預設 0.0 表示不啟用)
    take_profit_env = os.getenv("TAKE_PROFIT_PCT", "0.0")
    stop_loss_env = os.getenv("STOP_LOSS_PCT", "0.0")
    
    take_profit_pct = float(take_profit_env)
    stop_loss_pct = float(stop_loss_env)
    
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
    
    print(f"Config: {config}")
    
    # 執行回測
    result = run_backtest(df, config)
    summary = result['summary']
    trades = result['trades'] # List[TradeRecord]
    
    # 輸出報告
    print("\n" + "="*50)
    print(f"BACKTEST REPORT (CLI)")
    print("="*50)
    print(f"Total Trades   : {summary.total_trades}")
    print(f"Total Profit   : NT$ {summary.total_profit:,.0f}")
    print(f"Total ROI      : {summary.roi:.2f}%")
    print(f"Win Rate       : {summary.win_rate:.2f}%")
    print("-" * 50)
    
    if trades:
        df_trades = pd.DataFrame([t.__dict__ for t in trades])
        print("Top 3 Profitable Trades:")
        print(df_trades.sort_values('profit', ascending=False).head(3)[['symbol', 'name', 'buy_date', 'profit']].to_string(index=False))
        print("-" * 50)
        print("Top 3 Loss Trades:")
        print(df_trades.sort_values('profit', ascending=True).head(3)[['symbol', 'name', 'buy_date', 'profit']].to_string(index=False))

if __name__ == "__main__":
    main()
