#!/bin/bash
# 注意: 容器內通常沒有 date -j (BSD style), 而是 date -d (GNU style)
# 但為了相容性，我們改用 Python 來產生日期序列，這樣最穩

python3 -c "
import sys
from datetime import datetime, timedelta
import subprocess
import os

start_date = datetime.strptime('20200101', '%Y%m%d')
end_date = datetime.strptime('20260206', '%Y%m%d')
delta = timedelta(days=1)

curr = start_date
while curr <= end_date:
    d_str = curr.strftime('%Y%m%d')
    # 檢查目錄是否存在
    if os.path.exists(f'data/processed/daily_quotes/date={d_str}'):
        print(f'Checking {d_str}...')
        # 直接呼叫 checker
        res = subprocess.run(['python3', 'data_quality_checker.py'], env={**os.environ, 'START_DATE': d_str})
        if res.returncode != 0:
            print(f'❌ Issues found in {d_str}')
    
    curr += delta
"
