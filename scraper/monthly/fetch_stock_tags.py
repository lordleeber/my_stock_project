import requests
import pandas as pd
import os
import re
import time
import urllib3
import argparse
from io import StringIO

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.moneydj.com"
MAIN_PAGE = f"{BASE_URL}/z/zh/zha/zha.djhtm"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def _get_session(insecure=False):
    s = requests.Session()
    s.headers.update(HEADERS)
    s.verify = not insecure
    return s

def _decode_response(resp):
    # MoneyDJ often uses Big5; fall back to apparent encoding.
    if not resp.encoding:
        resp.encoding = resp.apparent_encoding
    if resp.encoding.lower() in ("iso-8859-1", "latin-1"):
        resp.encoding = "big5"
    return resp.text

def get_all_categories(session):
    print(f"Fetching main category page: {MAIN_PAGE}")
    try:
        res = session.get(MAIN_PAGE, timeout=30)
        res.raise_for_status()
        text = _decode_response(res)
        # 直接在原始 HTML 中用正則找連結，不依賴解析器
        matches = re.findall(
            r'href="(/z/zh/zha/zh\d{2}\.djhtm\?a=([^"&]+))"[^>]*>([^<]+)</a>',
            text
        )
        
        categories = []
        for href, cat_id, name in matches:
            categories.append({'name': name.strip(), 'id': cat_id, 'url': f"{BASE_URL}{href}"})
            
        # 去重
        unique = []
        seen = set()
        for c in categories:
            if c['id'] not in seen:
                unique.append(c)
                seen.add(c['id'])
        
        print(f"Found {len(unique)} unique categories.")
        return unique
    except Exception as e:
        print(f"Error: {e}")
        return []

def _parse_stocks_from_tables(html_text):
    try:
        tables = pd.read_html(StringIO(html_text))
    except Exception:
        return []
    symbols = set()
    for df in tables:
        if df.empty:
            continue
        # Some MoneyDJ tables embed header row inside the body.
        header_idx = None
        for i, row in df.iterrows():
            row_vals = [str(v).strip() for v in row.tolist()]
            if any(v == "股票名稱" for v in row_vals):
                header_idx = i
                break
        if header_idx is not None:
            df2 = df.copy()
            df2.columns = df2.iloc[header_idx].tolist()
            df2 = df2.iloc[header_idx + 1:]
            if "股票名稱" in df2.columns:
                codes = df2["股票名稱"].astype(str).str.extract(r"(\d{4})")[0].dropna()
                symbols.update(codes.tolist())
            continue

        cols = [str(c) for c in df.columns]
        if not any("代號" in c or "股票代號" in c or "Code" in c or "股票名稱" in c for c in cols):
            continue
        for col in df.columns:
            col_name = str(col)
            if "代號" in col_name or "Code" in col_name or "股票名稱" in col_name:
                codes = df[col].astype(str).str.extract(r"(\d{4})")[0].dropna()
                symbols.update(codes.tolist())
    return list(symbols)

def fetch_stocks_in_category(session, cat):
    try:
        res = session.get(cat['url'], timeout=20)
        res.raise_for_status()
        text = _decode_response(res)

        # 先嘗試解析表格
        symbols = _parse_stocks_from_tables(text)
        if symbols:
            return list(set(symbols))

        # 直接在文字內容中找股票代號連結
        # 格式: ZCA_1101.djhtm
        symbols = re.findall(r'ZCA_(\d{4})\.djhtm', text, re.IGNORECASE)
        return list(set(symbols))
    except:
        return []

def main():
    parser = argparse.ArgumentParser(description="Fetch MoneyDJ stock tags.")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification.")
    parser.add_argument("--max-categories", type=int, default=0, help="Limit categories for quick test.")
    args = parser.parse_args()

    session = _get_session(insecure=args.insecure)
    categories = get_all_categories(session)
    if not categories: return

    if args.max_categories > 0:
        categories = categories[:args.max_categories]
    
    results = []
    total = len(categories)
    raw_dir = "data/raw/stock_tags"
    os.makedirs(raw_dir, exist_ok=True)
    
    for i, cat in enumerate(categories):
        if i % 50 == 0:
            print(f"Progress: {i}/{total} categories processed...")
            
        stocks = fetch_stocks_in_category(session, cat)
        # print(f"  -> Found {len(stocks)} stocks for {cat['name']}")
        for symbol in stocks:
            results.append({'symbol': symbol, 'tag': cat['name']})
            
        time.sleep(0.3)
        
    if results:
        df = pd.DataFrame(results).drop_duplicates()
        output_path = os.path.join(raw_dir, "all.csv")
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        print(f"✅ Saved {len(df)} mappings.")
    else:
        print("❌ No results.")

if __name__ == "__main__":
    main()
