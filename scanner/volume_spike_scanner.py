"""
爆量翻多掃描器
找出類似 6548 (2025-10-03) 的爆量突破型態
"""

import os
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# 資料庫連線設定
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', 5432),
    'user': os.getenv('DB_USER', 'user'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'database': os.getenv('DB_NAME', 'stock_db')
}

def get_db_connection():
    """建立資料庫連線"""
    return psycopg2.connect(**DB_CONFIG)

def scan_volume_spike(scan_date, min_volume=5000000, volume_ratio=3.0, avg_days=10, filter_long_shadow=True):
    """
    掃描爆量股票

    參數:
        scan_date: 掃描日期 (格式: '2025-10-03')
        min_volume: 最小成交量門檻 (預設 500萬股)
        volume_ratio: 爆量倍數 (預設 3倍，與過去均量比較)
        avg_days: 計算平均量的天數 (預設 10日，可改為 5/20/60)
        filter_long_shadow: 是否過濾長上影線 (預設 True，過濾拉高出貨)

    回傳:
        DataFrame 包含符合條件的股票
    """

    conn = get_db_connection()

    query = """
    WITH volume_stats AS (
        -- 計算每支股票的過去10日平均量
        SELECT
            symbol,
            date,
            volume,
            AVG(volume) OVER (
                PARTITION BY symbol
                ORDER BY date
                ROWS BETWEEN %(avg_days)s PRECEDING AND 1 PRECEDING
            ) as avg_volume_nd,
            -- 計算過去20日最高價 (用來判斷是否接近前高)
            MAX(high) OVER (
                PARTITION BY symbol
                ORDER BY date
                ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
            ) as prev_high_20d
        FROM daily_quotes
        WHERE date <= %(scan_date)s
    ),
    candidates AS (
        SELECT
            dq.symbol,
            dq.name,
            dq.date,
            dq.open,
            dq.high,
            dq.low,
            dq.close,
            dq.volume,
            vs.avg_volume_nd,
            ROUND((dq.volume / NULLIF(vs.avg_volume_nd, 0))::numeric, 2) as volume_ratio,
            ROUND(((dq.close - vs.prev_high_20d) / NULLIF(vs.prev_high_20d, 0) * 100)::numeric, 2) as distance_from_high_pct,
            -- 計算上影線比例
            CASE
                WHEN dq.close > dq.open THEN
                    ROUND(((dq.high - dq.close) / NULLIF(dq.close - dq.open, 0))::numeric, 2)
                ELSE
                    ROUND(((dq.high - dq.open) / NULLIF(dq.open - dq.close, 0))::numeric, 2)
            END as upper_shadow_ratio,
            ti.ma5,
            ti.ma10,
            ti.ma20,
            ti.ma60,
            ti.k,
            ti.d,
            ti.rsi6,
            ti.rsi12,
            ti.macd_dif,
            ti.macd_dea
        FROM daily_quotes dq
        JOIN volume_stats vs ON dq.symbol = vs.symbol AND dq.date = vs.date
        LEFT JOIN technical_indicators ti ON dq.symbol = ti.symbol AND dq.date = ti.date
        WHERE dq.date = %(scan_date)s
          AND dq.volume >= %(min_volume)s
          AND vs.avg_volume_nd > 0
          AND dq.volume >= vs.avg_volume_nd * %(volume_ratio)s
          AND (%(filter_long_shadow)s = FALSE OR
               (ABS(dq.close - dq.open) >= 0.01 AND (dq.high - GREATEST(dq.open, dq.close)) / ABS(dq.close - dq.open) < 1.0))
          AND ti.ma60 IS NOT NULL AND dq.close >= ti.ma60
    )
    SELECT
        symbol,
        name,
        date,
        open,
        high,
        low,
        close,
        volume,
        volume_ratio,
        distance_from_high_pct,
        upper_shadow_ratio,
        ma5,
        ma10,
        ma20,
        ma60,
        k,
        d,
        rsi6,
        rsi12,
        macd_dif,
        macd_dea
    FROM candidates
    ORDER BY volume_ratio DESC
    """

    params = {
        'scan_date': scan_date,
        'min_volume': min_volume,
        'volume_ratio': volume_ratio,
        'avg_days': avg_days,
        'filter_long_shadow': filter_long_shadow
    }

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    return df

def analyze_stock_pattern(symbol, date, days_before=30, days_after=30):
    """
    分析單一股票在特定日期前後的走勢

    參數:
        symbol: 股票代號
        date: 分析日期
        days_before: 向前看幾天
        days_after: 向後看幾天

    回傳:
        DataFrame 包含該股票的歷史走勢
    """

    conn = get_db_connection()

    start_date = (datetime.strptime(date, '%Y-%m-%d') - timedelta(days=days_before)).strftime('%Y-%m-%d')
    end_date = (datetime.strptime(date, '%Y-%m-%d') + timedelta(days=days_after)).strftime('%Y-%m-%d')

    query = """
    SELECT
        dq.date,
        dq.close,
        dq.volume,
        ti.ma5,
        ti.ma10,
        ti.ma20,
        ti.k,
        ti.d,
        ti.rsi6
    FROM daily_quotes dq
    LEFT JOIN technical_indicators ti ON dq.symbol = ti.symbol AND dq.date = ti.date
    WHERE dq.symbol = %(symbol)s
      AND dq.date >= %(start_date)s
      AND dq.date <= %(end_date)s
    ORDER BY dq.date
    """

    params = {
        'symbol': symbol,
        'start_date': start_date,
        'end_date': end_date
    }

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    return df

def print_scan_results(df, top_n=10):
    """
    美化輸出掃描結果
    """
    if df.empty:
        print("❌ 未找到符合條件的股票")
        return

    print(f"\n✅ 找到 {len(df)} 支符合條件的股票\n")
    print("=" * 120)
    print(f"{'代號':<8} {'名稱':<10} {'開盤':<8} {'最高':<8} {'最低':<8} {'收盤':<8} {'量(萬)':<10} {'量比':<8} {'上影':<8} {'RSI6':<8}")
    print("=" * 120)

    for idx, row in df.head(top_n).iterrows():
        upper_shadow_str = f"{row['upper_shadow_ratio']:.2f}x" if pd.notna(row['upper_shadow_ratio']) else "N/A"
        print(f"{row['symbol']:<8} {row['name']:<10} {row['open']:<8.2f} {row['high']:<8.2f} {row['low']:<8.2f} "
              f"{row['close']:<8.2f} {row['volume']/10000:<10,.0f} {row['volume_ratio']:<8.2f} "
              f"{upper_shadow_str:<8} {row['rsi6']:<8.2f}")

    print("=" * 120)
    print("\n📊 技術指標說明:")
    print("  - 量比: 當日成交量 / 過去N日平均量 (預設N=10)")
    print("  - 上影: 上影線 / 實體 的比例 (>1.0 代表上影線比實體長，可能是拉高出貨)")
    print("  - RSI6: 6日相對強弱指標 (>70超買, <30超賣)")
    print("\n💡 使用建議:")
    print("  1. 量比 3-5 倍較健康，超過10倍要小心出貨")
    print("  2. 上影線比例 >1.0 要小心拉高出貨")
    print("  3. 預設已過濾長上影線，使用 --no-filter-shadow 關閉過濾\n")

def main():
    """主程式"""
    import argparse

    parser = argparse.ArgumentParser(description='爆量翻多掃描器')
    parser.add_argument('--date', type=str, required=True, help='掃描日期 (YYYY-MM-DD)')
    parser.add_argument('--min-volume', type=int, default=5000000, help='最小成交量 (預設500萬股)')
    parser.add_argument('--volume-ratio', type=float, default=3.0, help='爆量倍數 (預設3倍)')
    parser.add_argument('--avg-days', type=int, default=10, help='計算平均量天數 (預設10日，可選5/20/60)')
    parser.add_argument('--no-filter-shadow', dest='filter_long_shadow', action='store_false', help='不過濾長上影線 (預設會過濾)')
    parser.add_argument('--filter-long-shadow', dest='filter_long_shadow', action='store_true', help='過濾長上影線 (預設已開啟)')
    parser.set_defaults(filter_long_shadow=True)
    parser.add_argument('--top', type=int, default=10, help='顯示前N筆 (預設10)')
    parser.add_argument('--export', type=str, help='匯出CSV檔案路徑')
    parser.add_argument('--analyze', type=str, help='分析特定股票代號')

    args = parser.parse_args()

    print(f"\n🔍 掃描日期: {args.date}")
    print(f"📊 篩選條件: 成交量 >= {args.min_volume/10000:.0f}萬股, 量比 >= {args.volume_ratio}x (vs 過去{args.avg_days}日均量)")

    # 執行掃描
    df = scan_volume_spike(
        scan_date=args.date,
        min_volume=args.min_volume,
        volume_ratio=args.volume_ratio,
        avg_days=args.avg_days,
        filter_long_shadow=args.filter_long_shadow
    )

    # 顯示結果
    print_scan_results(df, top_n=args.top)

    # 匯出CSV
    if args.export and not df.empty:
        df.to_csv(args.export, index=False, encoding='utf-8-sig')
        print(f"✅ 結果已匯出至: {args.export}\n")

    # 分析特定股票
    if args.analyze and not df.empty:
        if args.analyze in df['symbol'].values:
            print(f"\n📈 分析 {args.analyze} 在 {args.date} 前後30天走勢:\n")
            analysis_df = analyze_stock_pattern(args.analyze, args.date)
            print(analysis_df.to_string(index=False))
        else:
            print(f"\n⚠️  {args.analyze} 未在掃描結果中")

if __name__ == '__main__':
    main()
