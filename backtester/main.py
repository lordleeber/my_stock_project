import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

def get_db_url():
    user = os.getenv("DB_USER") or "user"
    password = os.getenv("DB_PASSWORD") or "password"
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def fetch_data(engine):
    print("Fetching data for Backtest (2025-05-01 ~ 2025-06-15)...")
    # 我們需要抓取範圍稍微大一點，因為 5/31 的訊號需要 6 月的價格來結算
    query = """
        SELECT t.date, t.symbol, d.name, d.open, d.close, d.volume, t.vma10
        FROM technical_indicators t
        JOIN daily_quotes d ON t.symbol = d.symbol AND t.date = d.date
        WHERE t.date >= '2025-05-01' AND t.date <= '2025-06-15'
        ORDER BY t.symbol, t.date
    """
    df = pd.read_sql(query, engine)
    if df.empty:
        print("No data found.")
        return None
    
    df['date'] = pd.to_datetime(df['date'])
    return df

def generate_signals(df):
    # 標記訊號 (Signal)
    # 規則：Volume > 5 * VMA10
    df['vma10'] = df['vma10'].fillna(0)
    df['is_signal'] = df['volume'] > (df['vma10'] * 5)
    
    # 只保留 5月份產生的訊號
    mask_may = (df['date'] >= '2025-05-01') & (df['date'] <= '2025-05-31')
    signals = df[mask_may & df['is_signal']].copy()
    return signals

def execute_strategy(df, signals, mode='shares', capital=100000, fixed_shares=1000):
    trades = []
    
    for idx, row in signals.iterrows():
        symbol = row['symbol']
        signal_date = row['date']
        
        # 取得該股票的所有資料
        stock_data = df[df['symbol'] == symbol].reset_index(drop=True)
        
        # 找到訊號發生日在那張表中的索引
        try:
            # 取得訊號日的 index
            sig_idx_list = stock_data.index[stock_data['date'] == signal_date].tolist()
            if not sig_idx_list: continue
            sig_idx = sig_idx_list[0]
            
            # T+1 買進 (Open)
            buy_idx = sig_idx + 1
            # T+4 賣出 (Close) -> 買進後持有3個交易日
            sell_idx = sig_idx + 4 
            
            if buy_idx >= len(stock_data) or sell_idx >= len(stock_data):
                continue
                
            buy_row = stock_data.iloc[buy_idx]
            sell_row = stock_data.iloc[sell_idx]
            
            buy_price = float(buy_row['open'])
            sell_price = float(sell_row['close'])
            
            # 決定交易股數 (Position Size)
            shares = 0
            if mode == 'shares':
                shares = fixed_shares
            elif mode == 'amount':
                if buy_price > 0:
                    # 無條件捨去至整數股 (假設可買零股)
                    shares = int(capital // buy_price)
                else:
                    shares = 0
            
            if shares == 0:
                continue

            cost = buy_price * shares
            revenue = sell_price * shares
            profit = revenue - cost
            ret = (sell_price - buy_price) / buy_price if buy_price > 0 else 0
            
            trades.append({
                "symbol": symbol,
                "name": row['name'],
                "buy_date": buy_row['date'].date(),
                "sell_date": sell_row['date'].date(),
                "buy_price": buy_price,
                "sell_price": sell_price,
                "shares": shares,
                "cost": cost,
                "profit": profit,
                "return": ret
            })
            
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue
            
    return pd.DataFrame(trades)

def print_report(trades_df, title):
    if trades_df.empty:
        print(f"\n[{title}] No trades executed.")
        return

    total_profit = trades_df['profit'].sum()
    avg_return = trades_df['return'].mean() * 100
    win_rate = (trades_df['profit'] > 0).mean() * 100
    total_cost = trades_df['cost'].sum()
    roi = (total_profit / total_cost * 100) if total_cost > 0 else 0

    print("\n" + "="*50)
    print(f"BACKTEST REPORT: {title}")
    print("="*50)
    print(f"Executed Trades: {len(trades_df)}")
    print(f"Total Profit   : NT$ {total_profit:,.0f}")
    print(f"Total Cost     : NT$ {total_cost:,.0f}")
    print(f"Total ROI      : {roi:.2f}%")
    print(f"Win Rate       : {win_rate:.2f}%")
    print(f"Avg Return/Trade: {avg_return:.2f}%")
    print("-" * 50)
    print("Top 3 Profitable Trades:")
    print(trades_df.sort_values('profit', ascending=False).head(3)[['symbol', 'name', 'shares', 'buy_price', 'sell_price', 'profit']].to_string(index=False))
    print("-" * 50)
    print("Top 3 Loss Trades:")
    print(trades_df.sort_values('profit', ascending=True).head(3)[['symbol', 'name', 'shares', 'buy_price', 'sell_price', 'profit']].to_string(index=False))
    print("="*50)

def main():
    print("Starting Backtester...")
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    df = fetch_data(engine)
    if df is None: return
    
    signals = generate_signals(df)
    print(f"Found {len(signals)} signals in May 2025.")
    
    # 策略 1: 固定張數 (1張 = 1000股)
    trades_shares = execute_strategy(df, signals, mode='shares', fixed_shares=1000)
    print_report(trades_shares, "Strategy A: Fixed Shares (1000 shares/trade)")
    
    # 策略 2: 固定金額 (10萬元)
    trades_amount = execute_strategy(df, signals, mode='amount', capital=100000)
    print_report(trades_amount, "Strategy B: Fixed Amount (NT$ 100,000/trade)")

if __name__ == "__main__":
    main()