import os
import requests
import zipfile
import io
import argparse
from datetime import datetime
import time
from io import StringIO

import pandas as pd

FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"

# URL Templates
# 上市公司季報 = https://www.twse.com.tw/zh/trading/statistics/index05.html
SII_URL = "https://www.twse.com.tw/staticFiles/inspection/inspection/05/001/{year}Q{quarter}_C05001.zip"
# 上櫃公司季報 = https://www.tpex.org.tw/zh-tw/mainboard/listed/financial/summary.html
# 上櫃公司年季報為4月、6月、9月、12月第20個營業交易日更新。
OTC_URL = "https://www.tpex.org.tw/storage/statistic/financial/O_{year}Q{quarter}.xls"
MOPS_AJAX_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t163sb04"
MOPS_BALANCE_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t163sb05"
MOPS_CASHFLOW_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t163sb20"
RAW_DIR = "data/raw/quarterly_reports"
INCOME_STATEMENT_DIR = "data/raw/income_statement"
BALANCE_SHEET_DIR = "data/raw/balance_sheet"
CASH_FLOW_DIR = "data/raw/cash_flow"


def _convert_xls_to_raw_csv(xls_path, csv_path):
    """
    將 XLS 原始內容直接轉成 CSV（不做欄位標準化）。
    """
    try:
        df = pd.read_excel(xls_path, engine="xlrd", header=None)
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        return True
    except Exception as e:
        print(f"[!] Convert XLS->CSV failed ({xls_path}): {e}")
        return False


def download_sii(year, quarter, target_dir):
    """下載並解壓上市公司季報 ZIP，確保存為 sii.xls"""
    url = SII_URL.format(year=year, quarter=quarter)
    target_file = os.path.join(target_dir, "sii.xls")
    target_csv = os.path.join(target_dir, "sii.csv")
    if os.path.exists(target_file) and not FORCE_REPROCESS:
        if os.path.exists(target_csv):
            print(
                f"[=] SII report already exists at {target_file}, skip. (Set FORCE_REPROCESS=1 to overwrite)"
            )
            return True
        ok = _convert_xls_to_raw_csv(target_file, target_csv)
        if ok:
            print(f"[+] SII raw CSV saved to {target_csv}")
        return ok

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
            ok = _convert_xls_to_raw_csv(target_file, target_csv)
            if ok:
                print(f"[+] SII raw CSV saved to {target_csv}")
            return ok
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
    target_csv = os.path.join(target_dir, "otc.csv")
    if os.path.exists(target_file) and not FORCE_REPROCESS:
        if os.path.exists(target_csv):
            print(
                f"[=] OTC report already exists at {target_file}, skip. (Set FORCE_REPROCESS=1 to overwrite)"
            )
            return True
        ok = _convert_xls_to_raw_csv(target_file, target_csv)
        if ok:
            print(f"[+] OTC raw CSV saved to {target_csv}")
        return ok

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        print(f"[*] Fetching OTC: {url}")
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            with open(target_file, "wb") as f:
                f.write(resp.content)
            print(f"[+] OTC report saved to {target_file}")
            ok = _convert_xls_to_raw_csv(target_file, target_csv)
            if ok:
                print(f"[+] OTC raw CSV saved to {target_csv}")
            return ok
        else:
            print(f"[-] OTC not found (Status {resp.status_code})")
            return False
    except Exception as e:
        print(f"[!] OTC Error: {e}")
        return False


def _year_quarter_dir(base_dir, year, quarter):
    return os.path.join(base_dir, str(year), f"{year}Q{quarter}")


def download_quarterly_report(year, quarter, output_base_dir):
    m_ok = download_mops_income_statement(year, quarter, INCOME_STATEMENT_DIR)
    b_ok = download_mops_balance_sheet(year, quarter, BALANCE_SHEET_DIR)
    c_ok = download_mops_cash_flow(year, quarter, CASH_FLOW_DIR)

    return m_ok and b_ok and c_ok


def _post_mops(payload, url=MOPS_AJAX_URL):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    return requests.post(url, data=payload, headers=headers, timeout=30)


def _table_label(cols):
    joined = " ".join(cols)
    if any(
        k in joined
        for k in [
            "營業活動之淨現金流入",
            "投資活動之淨現金流入",
            "籌資活動之淨現金流入",
            "期末現金及約當現金",
        ]
    ):
        if any(
            k in joined
            for k in [
                "利息淨收益",
                "存放央行及拆借銀行同業",
                "貼現及放款",
                "存款及匯款",
            ]
        ):
            return "cashflow_bank"
        if any(k in joined for k in ["保險", "再保險", "保險負債"]):
            return "cashflow_insurance"
        return "cashflow_general"
    # Balance sheet subtype detection first
    if any(
        k in joined
        for k in ["資產總計", "資產總額", "負債總計", "負債總額", "權益總額"]
    ):
        if any(
            k in joined
            for k in ["存款及匯款", "貼現及放款", "附買回票券", "央行及同業融資"]
        ):
            return "bank"
        if any(k in joined for k in ["保險負債", "再保險", "保險合約"]):
            return "insurance"
        if any(
            k in joined for k in ["流動資產", "非流動資產", "流動負債", "非流動負債"]
        ):
            return "general"
        return "balance"
    if any(k in joined for k in ["利息淨收益", "利息以外淨收益", "呆帳"]):
        return "bank"
    if any(k in joined for k in ["保險", "保險負債準備", "保險負債"]):
        return "insurance"
    if any(k in joined for k in ["營業收入", "營業成本", "營業毛利"]):
        return "general"
    return "table"


def _save_tables_as_csv(resp_text, target_dir, market):
    if "<table" not in resp_text:
        return []
    try:
        tables = pd.read_html(StringIO(resp_text))
    except Exception:
        return []
    if not tables:
        return []

    labeled = []
    for df in tables:
        if df.empty:
            continue
        # Keep only tables that look like company data
        cols = [str(c) for c in df.columns]
        if not any("公司" in c or "代號" in c or "Code" in c for c in cols):
            continue
        # Drop header-like rows duplicated in body
        first_col = df.columns[0]
        df = df[df[first_col].astype(str).str.match(r"^\d{4}")].copy()
        if df.empty:
            continue
        label = _table_label(cols)
        labeled.append((label, df))

    if not labeled:
        return []

    os.makedirs(target_dir, exist_ok=True)
    label_counts = {}
    outputs = []
    for label, df in labeled:
        label_counts[label] = label_counts.get(label, 0) + 1
        suffix = f"{label}{label_counts[label]}" if label_counts[label] > 1 else label
        target_file = os.path.join(target_dir, f"{market}_{suffix}.csv")
        if os.path.exists(target_file) and not FORCE_REPROCESS:
            outputs.append(target_file)
            continue
        df.to_csv(target_file, index=False, encoding="utf-8-sig")
        outputs.append(target_file)
    return outputs


def download_mops_income_statement(year, quarter, output_base_dir):
    """抓取 MOPS 綜合損益表 (t163sb04)，存成多個 CSV。"""
    target_dir = _year_quarter_dir(output_base_dir, year, quarter)
    os.makedirs(target_dir, exist_ok=True)
    ok = False
    for market, typek in (("sii", "sii"), ("otc", "otc")):
        print(
            f"[*] Fetching MOPS t163sb04 Income Statement ({market.upper()}) {year}Q{quarter}"
        )
        # First try AD year (YYYY)
        payload = {
            "encodeURIComponent": 1,
            "step": 1,
            "firstin": 1,
            "off": 1,
            "TYPEK": typek,
            "year": str(year),
            "season": str(quarter),
        }
        try:
            resp = _post_mops(payload, url=MOPS_AJAX_URL)
            resp.encoding = "utf-8"
            outputs = _save_tables_as_csv(resp.text, target_dir, market)
            if outputs:
                print(f"[+] MOPS {market.upper()} saved: {', '.join(outputs)}")
                ok = True
                continue
        except Exception as e:
            print(f"[!] MOPS {market.upper()} error (AD year): {e}")

        # Fallback to ROC year
        roc_year = year - 1911
        payload["year"] = str(roc_year)
        try:
            resp = _post_mops(payload, url=MOPS_AJAX_URL)
            resp.encoding = "utf-8"
            outputs = _save_tables_as_csv(resp.text, target_dir, market)
            if outputs:
                print(
                    f"[+] MOPS {market.upper()} saved: {', '.join(outputs)} (ROC year)"
                )
                ok = True
            else:
                print(f"[-] MOPS {market.upper()} no table for {year}Q{quarter}")
        except Exception as e:
            print(f"[!] MOPS {market.upper()} error (ROC year): {e}")
    return ok


def download_mops_balance_sheet(year, quarter, output_base_dir):
    """抓取 MOPS 資產負債表 (t163sb05)，存成多個 CSV。"""
    target_dir = _year_quarter_dir(output_base_dir, year, quarter)
    os.makedirs(target_dir, exist_ok=True)
    ok = False
    for market, typek in (("sii", "sii"), ("otc", "otc")):
        print(
            f"[*] Fetching MOPS t163sb05 Balance Sheet ({market.upper()}) {year}Q{quarter}"
        )
        payload = {
            "encodeURIComponent": 1,
            "step": 1,
            "firstin": 1,
            "off": 1,
            "TYPEK": typek,
            "year": str(year),
            "season": str(quarter),
        }
        try:
            resp = _post_mops(payload, url=MOPS_BALANCE_URL)
            resp.encoding = "utf-8"
            outputs = _save_tables_as_csv(resp.text, target_dir, market)
            if outputs:
                print(f"[+] MOPS {market.upper()} saved: {', '.join(outputs)}")
                ok = True
                continue
        except Exception as e:
            print(f"[!] MOPS {market.upper()} error (AD year): {e}")

        roc_year = year - 1911
        payload["year"] = str(roc_year)
        try:
            resp = _post_mops(payload, url=MOPS_BALANCE_URL)
            resp.encoding = "utf-8"
            outputs = _save_tables_as_csv(resp.text, target_dir, market)
            if outputs:
                print(
                    f"[+] MOPS {market.upper()} saved: {', '.join(outputs)} (ROC year)"
                )
                ok = True
            else:
                print(f"[-] MOPS {market.upper()} no table for {year}Q{quarter}")
        except Exception as e:
            print(f"[!] MOPS {market.upper()} error (ROC year): {e}")
    return ok


def download_mops_cash_flow(year, quarter, output_base_dir):
    """抓取 MOPS 現金流量表 (t163sb20)，存成多個 CSV。"""
    target_dir = _year_quarter_dir(output_base_dir, year, quarter)
    os.makedirs(target_dir, exist_ok=True)
    ok = False
    for market, typek in (("sii", "sii"), ("otc", "otc")):
        print(
            f"[*] Fetching MOPS t163sb20 Cash Flow ({market.upper()}) {year}Q{quarter}"
        )
        payload = {
            "encodeURIComponent": 1,
            "step": 1,
            "firstin": 1,
            "off": 1,
            "TYPEK": typek,
            "year": str(year),
            "season": str(quarter),
        }
        try:
            resp = _post_mops(payload, url=MOPS_CASHFLOW_URL)
            resp.encoding = "utf-8"
            outputs = _save_tables_as_csv(resp.text, target_dir, market)
            if outputs:
                print(f"[+] MOPS {market.upper()} saved: {', '.join(outputs)}")
                ok = True
                continue
        except Exception as e:
            print(f"[!] MOPS {market.upper()} error (AD year): {e}")

        roc_year = year - 1911
        payload["year"] = str(roc_year)
        try:
            resp = _post_mops(payload, url=MOPS_CASHFLOW_URL)
            resp.encoding = "utf-8"
            outputs = _save_tables_as_csv(resp.text, target_dir, market)
            if outputs:
                print(
                    f"[+] MOPS {market.upper()} saved: {', '.join(outputs)} (ROC year)"
                )
                ok = True
            else:
                print(f"[-] MOPS {market.upper()} no table for {year}Q{quarter}")
        except Exception as e:
            print(f"[!] MOPS {market.upper()} error (ROC year): {e}")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Quarterly Financial Reports (SII & OTC)"
    )
    parser.add_argument("--year", type=int, help="Year (AD, e.g. 2020)")
    parser.add_argument(
        "--quarter", type=int, choices=[1, 2, 3, 4], help="Quarter (1-4)"
    )
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
        if q == 1:
            y -= 1
            q = 4
        else:
            q -= 1
        download_quarterly_report(y, q, RAW_DIR)


if __name__ == "__main__":
    main()
