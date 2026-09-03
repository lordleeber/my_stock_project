import os
import time
import requests
import pathlib
import datetime
import pandas as pd
import csv
import urllib3
from io import StringIO
from common.constants import CATEGORY_MAP

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 櫃買中心 (TPEx) API 網址設定
CATEGORY_DIC = {
    "每日收盤行情": "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&o=csv&d={date_tw}&se=EW&s=0,asc,0",
    "三大法人買賣金額統計表": "https://www.tpex.org.tw/web/stock/3insti/3insti_summary/3itrdsum_result.php?l=zh-tw&t=D&p=1&d={date_tw}&o=csv",
    "三大法人買賣超日報": "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=csv&se=EW&t=D&d={date_tw}&s=0,asc",
    "外資及陸資投資持股統計": "MOPS_SPECIAL_HANDLING",
    "融資融券": "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=csv&charset=UTF-8&d={date_tw}&c=&s=0,asc",
    "融券借券": "https://www.tpex.org.tw/web/stock/margin_trading/margin_sbl/margin_sbl_result.php?l=zh-tw&d={date_tw}&s=0,asc&o=csv",
    "本益比殖利率淨值": "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php?l=zh-tw&o=csv&charset=UTF-8&d={date_tw}&c=&s=0,asc",
    "指數行情": "https://www.tpex.org.tw/www/zh-tw/afterTrading/indexSummary",  # 現代化 API 路徑
}

REFERER_DIC = {
    "指數行情": "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/indices-pricing.html"
}

EMPTY_SIZE_DIC = {
    "每日收盤行情": 5000,
    "三大法人買賣金額統計表": 300,
    "三大法人買賣超日報": 5000,
    "外資及陸資投資持股統計": 5000,
    "融資融券": 5000,
    "融券借券": 5000,
    "本益比殖利率淨值": 5000,
}

COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/json,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
}

FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"


def to_tw_date(date_str):
    year = int(date_str[0:4]) - 1911
    return f"{year}/{date_str[4:6]}/{date_str[6:8]}"


def fetch_tpex_index_json(date_string, dst_file_path):
    """
    實作與舊版 fetch_tpex_index_summary.py 類似的抓取邏輯
    """
    url_base = CATEGORY_DIC["指數行情"]
    # 嘗試多種日期格式
    year_tw = int(date_string[0:4]) - 1911
    date_candidates = [
        date_string,
        f"{date_string[0:4]}/{date_string[4:6]}/{date_string[6:8]}",
        f"{year_tw}/{date_string[4:6]}/{date_string[6:8]}",
        f"{year_tw:03d}{date_string[4:6]}{date_string[6:8]}",
    ]

    last_error = None
    for cand in date_candidates:
        url = f"{url_base}?date={cand}&response=json"
        try:
            res = requests.get(url, headers=COMMON_HEADERS, verify=False, timeout=20)
            if res.status_code != 200:
                last_error = f"candidate '{cand}': status code {res.status_code}"
            else:
                obj = res.json()
                if "tables" not in obj or len(obj["tables"]) == 0:
                    last_error = f"candidate '{cand}': response has no tables"
                else:
                    # 尋找「上櫃股價指數收盤行情」表格
                    target_table = None
                    for t in obj["tables"]:
                        if "上櫃股價指數收盤行情" in t.get("title", ""):
                            target_table = t
                            break

                    if not target_table:
                        target_table = obj["tables"][0]

                    fields = target_table.get("fields", [])
                    data = target_table.get("data", [])
                    if data:
                        df = pd.DataFrame(data, columns=fields)
                        df.to_csv(
                            dst_file_path,
                            index=False,
                            encoding="utf-8-sig",
                            quoting=csv.QUOTE_ALL,
                        )
                        print(
                            f"[{date_string}] OTC Index saved successfully using candidate '{cand}'"
                        )
                        return True
                    last_error = f"candidate '{cand}': table has no data rows"
        except Exception as e:
            last_error = f"candidate '{cand}': {type(e).__name__}: {e}"
            continue
    print(
        f"[{date_string}] Failed to fetch OTC Index after trying all date formats. "
        f"Last error: {last_error}"
    )
    return False


def fetch_data(date_string, category, output_dir):
    eng_category = CATEGORY_MAP.get(category, category)
    # 結構變更: raw/{category}/yyyy/yyyymmdd/
    year = date_string[:4]
    dst_folder = os.path.join(output_dir, "raw", eng_category, year, date_string)
    pathlib.Path(dst_folder).mkdir(parents=True, exist_ok=True)
    dst_file_path = os.path.join(dst_folder, "otc.csv")

    if os.path.exists(dst_file_path):
        if FORCE_REPROCESS:
            print(
                f"[{date_string}] OTC {eng_category} exists, reprocessing due to FORCE_REPROCESS=1."
            )
        else:
            print(f"[{date_string}] OTC {eng_category} already exists, skip.")
            return

    if category == "指數行情":
        fetch_tpex_index_json(date_string, dst_file_path)
        return

    if category == "外資及陸資投資持股統計":
        # (保留原本 MOPS 邏輯)
        from bs4 import BeautifulSoup

        url = "https://mopsov.twse.com.tw/server-java/t13sa150_otc"
        year = int(date_string[0:4])
        month = date_string[4:6]
        day = date_string[6:8]
        payload = {
            "step": "2",
            "years": str(year),
            "months": month,
            "days": day,
            "bcode": "",
        }
        try:
            res = requests.post(url, data=payload, headers=COMMON_HEADERS, verify=False)
            soup = BeautifulSoup(res.content, "html.parser", from_encoding="big5")
            rows = soup.find_all("tr")
            data = []
            for row in rows:
                cols = row.find_all(["td", "th"])
                cols_text = [ele.get_text(strip=True) for ele in cols]
                if len(cols_text) > 5:
                    data.append(cols_text)
            if not data:
                print(
                    f"[{date_string}] OTC {eng_category} is empty or no data. "
                    f"(MOPS returned no parsable rows, status {res.status_code})"
                )
                return
            df = pd.DataFrame(data)
            for i in range(len(df)):
                if any("證券代號" in str(x) for x in df.iloc[i].values):
                    df.columns = df.iloc[i]
                    df = df.iloc[i + 1 :]
                    break
            if "證券代號" in df.columns:
                df = df[
                    ~df["證券代號"]
                    .astype(str)
                    .str.contains("證券代號|說明|註|因素", na=False)
                ]
            df.to_csv(
                dst_file_path,
                index=False,
                encoding="utf-8-sig",
                quoting=csv.QUOTE_ALL,
            )
            print(f"[{date_string}] OTC Foreign Hold saved.")
        except Exception as e:
            print(
                f"[{date_string}] Error fetching OTC {eng_category}: {type(e).__name__}: {e}"
            )
        return

    date_tw = to_tw_date(date_string)
    url = CATEGORY_DIC[category].format(date_tw=date_tw)
    headers = COMMON_HEADERS.copy()
    headers["Referer"] = REFERER_DIC.get(category, "https://www.tpex.org.tw/")

    try:
        response = requests.get(url, headers=headers, timeout=30, verify=False)
        if response.status_code != 200:
            print(
                f"[{date_string}] Failed to fetch OTC {eng_category}. "
                f"Status code: {response.status_code}"
            )
            return
        # TPEx 的 404 頁面回的是 status 200 + UTF-8 的 HTML（`<meta charset="utf-8">`），
        # 但 CSV 端點回的是 MS950/big5。不能用 response.text 比對：那頁的
        # Content-Type 是裸的 `text/html` 沒有 charset，requests 依 HTTP 規範
        # 退回 ISO-8859-1，中文全變 mojibake，marker 永遠對不上。而那頁約 10 KB、
        # 遠超過 5000 門檻，於是錯誤頁會被當成正常回應寫進 otc.csv，
        # 再被 check_outputs.py 的 (>=10 bytes, >=2 行) 放行送進 processor。
        if "404 - 證券櫃檯買賣中心" in response.content.decode(
            "utf-8", errors="ignore"
        ):
            print(
                f"[{date_string}] Failed to fetch OTC {eng_category}. "
                f"TPEx returned its 404 page."
            )
            return
        min_size = EMPTY_SIZE_DIC.get(category, 0)
        if len(response.content) <= min_size:
            print(
                f"[{date_string}] OTC {eng_category} is empty or no data. "
                f"({len(response.content)} bytes <= {min_size} threshold)"
            )
            return

        content = response.content.decode("big5", errors="ignore")
        f_in = StringIO(content)
        reader = csv.reader(f_in)
        f_out = StringIO()
        writer = csv.writer(f_out, quoting=csv.QUOTE_ALL)
        for row in reader:
            clean_row = [
                c.strip()[2:-1] if c.strip().startswith('="') else c.strip()
                for c in row
            ]
            if len(clean_row) > 1:
                writer.writerow(clean_row)
        csv_content = f_out.getvalue()
        if not csv_content.strip():
            print(f"[{date_string}] OTC {eng_category} is empty or no data.")
        else:
            with open(dst_file_path, "w", encoding="utf-8-sig") as f:
                f.write(csv_content)
            print(f"[{date_string}] OTC {eng_category} saved.")
    except Exception as e:
        print(
            f"[{date_string}] Error fetching OTC {eng_category}: {type(e).__name__}: {e}"
        )


def run_scraper(date_list, output_dir, delay=3.0):
    for date_str in date_list:
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
        date_list = [
            (start + datetime.timedelta(days=i)).strftime("%Y%m%d")
            for i in range((end - start).days + 1)
        ]
    else:
        date_list = [datetime.datetime.today().strftime("%Y%m%d")]
    run_scraper(date_list, output_dir, float(os.getenv("FETCH_DELAY", "3.0")))
