import os
import time
import requests
import pathlib
import datetime
import csv
from io import StringIO
from common.constants import CATEGORY_MAP

# 證交所 API 網址設定
CATEGORY_DIC = {
    "每日收盤行情": "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=csv&date={date}&type=ALLBUT0999",
    "三大法人買賣金額統計表": "https://www.twse.com.tw/fund/BFI82U?response=csv&dayDate={date}&type=day",
    "三大法人買賣超日報": "https://www.twse.com.tw/fund/T86?response=csv&date={date}&selectType=ALLBUT0999",
    "外資及陸資投資持股統計": "https://www.twse.com.tw/fund/MI_QFIIS?response=csv&date={date}&selectType=ALLBUT0999",
    "融資融券": "https://www.twse.com.tw/exchangeReport/MI_MARGN?response=csv&date={date}&selectType=ALL",
    "融券借券": "https://www.twse.com.tw/exchangeReport/TWT93U?response=csv&date={date}",
    "本益比殖利率淨值": "https://www.twse.com.tw/exchangeReport/BWIBBU_d?response=csv&date={date}&selectType=ALL",
}

# 最小檔案大小檢查 (避免存下錯誤或空的 CSV)
EMPTY_SIZE_DIC = {
    "每日收盤行情": 0,
    "三大法人買賣金額統計表": 2,
    "三大法人買賣超日報": 2,
    "外資及陸資投資持股統計": 2498,
    "融資融券": 818,
    "融券借券": 1616,
    "本益比殖利率淨值": 2,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"


def fetch_data(date_string, category, output_dir):
    url = CATEGORY_DIC[category].format(date=date_string)

    eng_category = CATEGORY_MAP.get(category, category)
    # 結構變更: raw/{category}/yyyy/yyyymmdd/
    year = date_string[:4]
    dst_folder = os.path.join(output_dir, "raw", eng_category, year, date_string)
    pathlib.Path(dst_folder).mkdir(parents=True, exist_ok=True)

    # 檔名變更: sii.csv
    dst_file_path = os.path.join(dst_folder, "sii.csv")

    if os.path.exists(dst_file_path):
        if FORCE_REPROCESS:
            print(
                f"[{date_string}] SII {eng_category} exists, reprocessing due to FORCE_REPROCESS=1."
            )
        else:
            print(f"[{date_string}] SII {eng_category} already exists, skip.")
            return

    try:
        print(f"Fetching SII {eng_category} for {date_string}...")
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            if len(response.content) <= EMPTY_SIZE_DIC.get(category, 0):
                print(f"[{date_string}] SII {eng_category} is empty or no data.")
            else:
                content = response.content.decode("big5", errors="ignore")
                f_in = StringIO(content)
                reader = csv.reader(f_in)
                f_out = StringIO()
                writer = csv.writer(f_out, quoting=csv.QUOTE_ALL)
                for row in reader:
                    clean_row = []
                    for cell in row:
                        cell = cell.strip()
                        # Remove Excel anti-formatting wrapper ="..."
                        if cell.startswith('="') and cell.endswith('"'):
                            cell = cell[2:-1]
                        clean_row.append(cell)

                    # 只有欄位數大於 1 的行才寫入 (過濾掉標題與檔尾說明)
                    if len(clean_row) > 1:
                        writer.writerow(clean_row)
                with open(dst_file_path, "w", encoding="utf-8-sig") as f:
                    f.write(f_out.getvalue())
                print(
                    f"[{date_string}] SII {eng_category} saved and cleaned to {dst_file_path}"
                )
        else:
            print(
                f"[{date_string}] Failed to fetch {eng_category}. Status code: {response.status_code}"
            )
    except Exception as e:
        print(f"[{date_string}] Error fetching {eng_category}: {e}")


def run_scraper(date_list, output_dir, delay=3.0):
    for date_str in date_list:
        if datetime.datetime.strptime(date_str, "%Y%m%d") > datetime.datetime.today():
            continue
        for category in CATEGORY_DIC:
            fetch_data(date_str, category, output_dir)
            time.sleep(delay)


if __name__ == "__main__":
    output_dir = os.getenv("OUTPUT_DIR", "data")
    start_date_env = os.getenv("START_DATE")
    end_date_env = os.getenv("END_DATE")
    if start_date_env and end_date_env:
        start = datetime.datetime.strptime(start_date_env, "%Y%m%d")
        end = datetime.datetime.strptime(end_date_env, "%Y%m%d")
        delta = end - start
        date_list = [
            (start + datetime.timedelta(days=i)).strftime("%Y%m%d")
            for i in range(delta.days + 1)
        ]
    else:
        date_list = [datetime.datetime.today().strftime("%Y%m%d")]
    delay = float(os.getenv("FETCH_DELAY", "3.0"))
    run_scraper(date_list, output_dir, delay)
