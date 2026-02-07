import os
import requests
import zipfile
import io
import argparse
from datetime import datetime
import time

# URL Templates
SII_URL = "https://www.twse.com.tw/staticFiles/inspection/inspection/05/001/{year}Q{quarter}_C05001.zip"
OTC_URL = "https://www.tpex.org.tw/storage/statistic/financial/O_{year}Q{quarter}.xls"
RAW_DIR = "data/raw/quarterly_reports"

def download_sii(year, quarter, target_dir):
    """下載並解壓上市公司季報 ZIP，確保存為 sii.xls"""
    url = SII_URL.format(year=year, quarter=quarter)
    target_file = os.path.join(target_dir, "sii.xls")
    
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        print(f"[*] Fetching SII: {url}")
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                file_list = z.namelist()
                if file_list:
                    # 抓取 ZIP 內第一個檔案並寫入 sii.xls
                    with z.open(file_list[0]) as source:
                        content = source.read()
                        with open(target_file, "wb") as f:
                            f.write(content)
            print(f"[+] SII report saved to {target_file}")
            return True
        else:
            print(f"[-] SII not found (Status {resp.status_code})")
            return False
    except Exception as e:
        print(f"[!] SII Error: {e}")
        return False

def download_otc(year, quarter, target_dir):
    """直接下載上櫃公司季報 XLS，確保存為 otc.xls"""
    url = OTC_URL.format(year=year, quarter=quarter)
    target_file = os.path.join(target_dir, "otc.xls")
    
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        print(f"[*] Fetching OTC: {url}")
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            with open(target_file, "wb") as f:
                f.write(resp.content)
            print(f"[+] OTC report saved to {target_file}")
            return True
        else:
            print(f"[-] OTC not found (Status {resp.status_code})")
            return False
    except Exception as e:
        print(f"[!] OTC Error: {e}")
        return False

def download_quarterly_report(year, quarter, output_base_dir):
    target_dir = os.path.join(output_base_dir, f"date={year}Q{quarter}")
    os.makedirs(target_dir, exist_ok=True)
    
    s_ok = download_sii(year, quarter, target_dir)
    time.sleep(2) # 禮貌性延遲
    o_ok = download_otc(year, quarter, target_dir)
    
    return s_ok or o_ok

def main():
    parser = argparse.ArgumentParser(description="Fetch Quarterly Financial Reports (SII & OTC)")
    parser.add_argument("--year", type=int, help="Year (AD, e.g. 2020)")
    parser.add_argument("--quarter", type=int, choices=[1, 2, 3, 4], help="Quarter (1-4)")
    parser.add_argument("--all", action="store_true", help="Fetch from 2020 to current")
    
    args = parser.parse_args()

    if args.all:
        current_year = datetime.now().year
        for y in range(2020, current_year + 1):
            for q in range(1, 5):
                if y == current_year and q > (datetime.now().month - 1) // 3 + 1:
                    continue
                print(f"\n>>> {y}Q{q} <<<")
                download_quarterly_report(y, q, RAW_DIR)
                time.sleep(3)
    elif args.year and args.quarter:
        download_quarterly_report(args.year, args.quarter, RAW_DIR)
    else:
        today = datetime.now()
        y, q = today.year, (today.month - 1) // 3 + 1
        if q == 1: y -= 1; q = 4
        else: q -= 1
        download_quarterly_report(y, q, RAW_DIR)

if __name__ == "__main__":
    main()