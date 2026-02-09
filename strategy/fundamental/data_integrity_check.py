import pandas as pd
import sys
import numpy as np
import os
import glob

# 加入專案根目錄到 path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.http_client import fetch_dataframe, fetch_json
from common.constants import API_BASE

# ---------------------------------------------------------
# 資料完整性檢測器 2.0 (共用模組 + 重試機制)
# ---------------------------------------------------------

if sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_integrity_check():
    START_DATE = "2020-01-01"
    END_DATE = "2026-02-06"

    print(f"=== 資料異常檢測 ({START_DATE} ~ {END_DATE}) ===")

    # 讀取關注名單 (改用最新的報告)
    report_path = "strategy/fundamental/fundamental_report_2025Q3.csv"
    if not os.path.exists(report_path):
        print(f"找不到 {report_path}，嘗試尋找任一報告...")
        files = glob.glob("strategy/fundamental/fundamental_report_*.csv")
        if files: report_path = files[-1]
        else:
            print("無報告可用。")
            return

    print(f"讀取名單: {report_path}")
    df_target = pd.read_csv(report_path)
    target_symbols = df_target['symbol'].astype(str).unique()
    print(f"鎖定掃描 {len(target_symbols)} 檔重點股票...")

    abnormal_records = []
    count = 0

    for symbol in target_symbols:
        count += 1
        if count % 50 == 0: print(f"  進度: {count}/{len(target_symbols)}...")

        try:
            df = fetch_dataframe("/raw/daily-quotes", {
                "symbol": symbol,
                "start_date": START_DATE,
                "end_date": END_DATE,
                "limit": 5000
            })
            if df.empty: continue

            df = df.sort_values('date')
            df['prev_close'] = df['close'].shift(1)
            df = df[df['prev_close'] > 0]

            df['pct_change'] = (df['close'] - df['prev_close']) / df['prev_close'] * 100

            # 檢查異常: > 11% 或 < -11%
            mask = (df['pct_change'] > 11) | (df['pct_change'] < -11)
            abnormal = df[mask]

            if not abnormal.empty:
                for _, row in abnormal.iterrows():
                    rec = {
                        'symbol': symbol,
                        'date': row['date'],
                        'pct_change': round(row['pct_change'], 2),
                        'prev': row['prev_close'],
                        'curr': row['close']
                    }
                    abnormal_records.append(rec)
                    print(f"  [警告] {symbol} @ {row['date']}: {rec['pct_change']}% ({rec['prev']} -> {rec['curr']})")

        except Exception as e:
            print(f"  [Error] {symbol}: {e}")

    if abnormal_records:
        out_path = "strategy/fundamental/data_anomalies.csv"
        pd.DataFrame(abnormal_records).to_csv(out_path, index=False)
        print(f"\n掃描完成！共發現 {len(abnormal_records)} 筆異常，已儲存至 {out_path}")
    else:
        print("\n掃描完成！全市場重點股票 (500+檔) 均無異常漲跌幅。")

if __name__ == "__main__":
    run_integrity_check()
