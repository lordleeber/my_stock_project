"""
K線圖繪製工具
"""

import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from sqlalchemy import create_engine

def get_db_url():
    user = os.getenv("DB_USER", "user")
    password = os.getenv("DB_PASSWORD", "password")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "stock_db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

def fetch_stock_data(symbol, start_date, end_date):
    """從資料庫撈取股票資料"""
    engine = create_engine(get_db_url())

    query = f"""
    SELECT
        dq.date,
        dq.open,
        dq.high,
        dq.low,
        dq.close,
        dq.volume,
        ti.ma5,
        ti.ma10,
        ti.ma20,
        ti.ma60
    FROM daily_quotes dq
    LEFT JOIN technical_indicators ti ON dq.symbol = ti.symbol AND dq.date = ti.date
    WHERE dq.symbol = '{symbol}'
      AND dq.date >= '{start_date}'
      AND dq.date <= '{end_date}'
    ORDER BY dq.date
    """

    df = pd.read_sql(query, engine)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)

    return df

def plot_candlestick(symbol, start_date, end_date, output_file=None):
    """繪製 K 線圖"""

    # 撈取資料
    df = fetch_stock_data(symbol, start_date, end_date)

    if df.empty:
        print(f"❌ 找不到 {symbol} 在 {start_date} ~ {end_date} 的資料")
        return

    # 準備 MA 線
    add_plots = []

    if df['ma5'].notna().any():
        add_plots.append(mpf.make_addplot(df['ma5'], color='orange', width=1))
    if df['ma10'].notna().any():
        add_plots.append(mpf.make_addplot(df['ma10'], color='blue', width=1))
    if df['ma20'].notna().any():
        add_plots.append(mpf.make_addplot(df['ma20'], color='red', width=1))
    if df['ma60'].notna().any():
        add_plots.append(mpf.make_addplot(df['ma60'], color='purple', width=1))

    # 設定樣式
    mc = mpf.make_marketcolors(
        up='red',      # 紅漲
        down='green',  # 綠跌
        edge='inherit',
        wick='inherit',
        volume='in'
    )

    s = mpf.make_mpf_style(
        marketcolors=mc,
        gridstyle='-',
        y_on_right=False
    )

    # 繪製圖表
    title = f'{symbol} K線圖 ({start_date} ~ {end_date})'

    fig, axes = mpf.plot(
        df,
        type='candle',
        style=s,
        title=title,
        ylabel='Price',
        volume=True,
        addplot=add_plots if add_plots else None,
        figsize=(14, 8),
        returnfig=True,
        datetime_format='%Y-%m-%d',
        xrotation=45
    )

    # 加上圖例
    axes[0].legend(['MA5', 'MA10', 'MA20', 'MA60'], loc='upper left')

    # 儲存或顯示
    if output_file:
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"✅ K線圖已儲存至: {output_file}")
    else:
        plt.show()

    plt.close()

def main():
    import argparse

    parser = argparse.ArgumentParser(description='繪製股票 K 線圖')
    parser.add_argument('--symbol', type=str, required=True, help='股票代號')
    parser.add_argument('--start', type=str, required=True, help='開始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='結束日期 (YYYY-MM-DD)')
    parser.add_argument('--output', type=str, help='輸出檔案路徑 (預設顯示圖表)')

    args = parser.parse_args()

    plot_candlestick(args.symbol, args.start, args.end, args.output)

if __name__ == '__main__':
    main()
