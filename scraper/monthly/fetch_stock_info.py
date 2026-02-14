import requests
import pandas as pd
import os
import re
import urllib3
from io import StringIO

# 忽略不安全請求警告 (針對 verify=False)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def fetch_stock_info(market_type):
    """
    抓取證交所證券編碼查詢頁面的股票基本資料。
    market_type: '1' 為上市, '2' 為上櫃
    """
    issue_type = '1' if market_type == '1' else '4'
    url = f"https://isin.twse.com.tw/isin/class_main.jsp?owncode=&stockname=&isincode=&market={market_type}&issuetype={issue_type}&industry_code=&Page=1&chklike=Y"
    market_label = "SII" if market_type == '1' else "OTC"
    
    print(f"Fetching {market_label} stock info from: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        # 該頁面使用 Big5 編碼
        res = requests.get(url, headers=headers, verify=False, timeout=30)
        res.raise_for_status()
        html_content = res.content.decode('big5', errors='ignore')
        
        # 使用 pandas 讀取表格
        dfs = pd.read_html(StringIO(html_content))
        
        target_df = None
        for df in dfs:
            if df.shape[1] >= 7:
                # 檢查第一行是否包含關鍵字
                row_str = "".join([str(x) for x in df.iloc[0].tolist()])
                if "有價證券代號" in row_str:
                    target_df = df
                    break
        
        if target_df is None:
            print(f"❌ Could not find data table for {market_label}")
            return None
            
        # 設定第一行為 header
        target_df.columns = target_df.iloc[0]
        target_df = target_df.iloc[1:].copy()
        
        # 清理欄位名稱
        orig_cols = [str(c).strip().replace(' ', '').replace('\n', '').replace('\r', '') for c in target_df.columns]
        target_df.columns = orig_cols
        # print(f"DEBUG: Original columns: {orig_cols}")
        
        # 映射欄位
        col_map = {
            '有價證券代號': 'symbol',
            '有價證券名稱': 'name',
            '產業別': 'industry',
            '上市日期': 'listing_date',
            '上櫃日期': 'listing_date',
            '發行日': 'listing_date' # 備用
        }
        
        # 遍歷所有欄位，只要包含「日期」或「發行」就嘗試匹配
        for c in target_df.columns:
            if ("日期" in c or "發行" in c) and "listing_date" not in target_df.columns:
                target_df = target_df.rename(columns={c: 'listing_date'})
        
        target_df = target_df.rename(columns=col_map)
        
        # 只保留需要的
        needed_cols = ['symbol', 'name', 'industry', 'listing_date']
        target_df = target_df[[c for c in needed_cols if c in target_df.columns]]
        target_df['market'] = market_label.lower()
        
        print(f"✅ Parsed {len(target_df)} {market_label} stocks.")
        return target_df

    except Exception as e:
        print(f"❌ Error fetching {market_label}: {e}")
        return None

def main():
    df_sii = fetch_stock_info('1')
    df_otc = fetch_stock_info('2')
    
    if df_sii is None and df_otc is None:
        print("No data fetched. Exiting.")
        return
        
    full_df = pd.concat([df for df in [df_sii, df_otc] if df is not None], ignore_index=True)
    
    # 確保代號是 4 位純數字
    full_df = full_df[full_df['symbol'].astype(str).str.match(r'^\d{4}$')]
    
    output_dir = "data/raw/stock_info"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "all.csv")
    
    full_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n✅ Successfully saved {len(full_df)} stocks to {output_path}")
    print(full_df[['symbol', 'name', 'industry', 'listing_date', 'market']].head())

if __name__ == "__main__":
    main()