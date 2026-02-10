#!/bin/bash
# 執行全面資料品質檢查
# 使用方式: ./run_full_check.sh <START_DATE> <END_DATE>
# 範例: ./run_full_check.sh 20200101 20200630

if [ -z "$1" ] || [ -z "$2" ]; then
    echo "Usage: $0 <START_DATE> <END_DATE>"
    echo "Example: $0 20200101 20200630"
    exit 1
fi

START=$1
END=$2

python3 -c "
import sys
from datetime import datetime, timedelta
import subprocess
import os

start_str = '$START'
end_str = '$END'

try:
    start_date = datetime.strptime(start_str, '%Y%m%d')
    end_date = datetime.strptime(end_str, '%Y%m%d')
except ValueError:
    print('Error: Invalid date format. Use YYYYMMDD.')
    sys.exit(1)

delta = timedelta(days=1)

print(f'Starting full check from {start_str} to {end_str}...')

curr = start_date
while curr <= end_date:
    d_str = curr.strftime('%Y%m%d')
    
    # 只針對交易日（週一至週五）進行檢查，且目錄必須存在
    # 如果您希望檢查缺失檔案，可以移除 os.path.exists 判斷
    if os.path.exists(f'data/processed/daily_quotes/date={d_str}'):
        print(f'Checking {d_str}...')
        res = subprocess.run(['python3', 'data_quality_checker.py'], env={**os.environ, 'START_DATE': d_str})
        if res.returncode != 0:
            print(f'❌ Issues found in {d_str}')
    
    curr += delta
"
