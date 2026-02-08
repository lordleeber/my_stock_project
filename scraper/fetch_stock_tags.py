import requests
import pandas as pd
import os
import re
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.moneydj.com"
MAIN_PAGE = f"{BASE_URL}/z/zh/zha/zha.djhtm"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_all_categories():
    print(f"Fetching main category page: {MAIN_PAGE}")
    try:
        res = requests.get(MAIN_PAGE, headers=headers, verify=False, timeout=30)
        res.raise_for_status()
        # 直接在原始 HTML 中用正則找連結，不依賴解析器
        matches = re.findall(r'href="(/z/zh/zha/zh00\.djhtm\?a=([^"]+))">([^<]+)</a>', res.text)
        
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

def fetch_stocks_in_category(cat):
    try:
        res = requests.get(cat['url'], headers=headers, verify=False, timeout=20)
        # 直接在文字內容中找股票代號連結
        # 格式: ZCA_1101.djhtm
        symbols = re.findall(r'ZCA_(\d{4})\.djhtm', res.text, re.IGNORECASE)
        return list(set(symbols))
    except:
        return []

def main():
    categories = get_all_categories()
    if not categories: return
    
    results = []
    total = len(categories)
    raw_dir = "data/raw/stock_tags"
    os.makedirs(raw_dir, exist_ok=True)
    
    for i, cat in enumerate(categories):
        if i % 50 == 0:
            print(f"Progress: {i}/{total} categories processed...")
            
        stocks = fetch_stocks_in_category(cat)
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