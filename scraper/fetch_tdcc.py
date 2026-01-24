import requests
import pandas as pd
import os
import io

# 集保全市場股權分散 Open Data 網址
TDCC_OPEN_DATA_URL = "https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
}

def fetch_tdcc_opendata(output_dir="data"):
    print(f"Downloading TDCC Open Data from {TDCC_OPEN_DATA_URL}...")
    
    try:
        # 使用 Session 並手動處理重定向，或者直接加上強大的 Headers
        session = requests.Session()
        response = session.get(TDCC_OPEN_DATA_URL, headers=HEADERS, timeout=60, allow_redirects=True)
        response.raise_for_status()
        
        # 檢查內容類型
        print(f"Content-Type: {response.headers.get('Content-Type')}")
        
        # 嘗試讀取 CSV
        df = pd.read_csv(io.BytesIO(response.content))
        
        if df.empty:
            print("Downloaded CSV is empty.")
            return None
            
        date_col = df.columns[0]
        data_date = str(df[date_col].iloc[0])
        print(f"Data Date identified: {data_date}")
        
        dst_folder = os.path.join(output_dir, "raw", "shareholding_div", f"date={data_date}")
        os.makedirs(dst_folder, exist_ok=True)
        
        dst_file = os.path.join(dst_folder, "all.csv")
        df.to_csv(dst_file, index=False, encoding='utf-8-sig')
        print(f"Saved TDCC data to {dst_file} ({len(df)} rows)")
        
        return data_date

    except Exception as e:
        print(f"Error fetching TDCC Open Data: {e}")
        # 如果失敗，印出 response 內容的前 500 字元供除錯
        if 'response' in locals() and response:
            print("Response preview:", response.text[:500])
        return None

if __name__ == "__main__":
    output_dir = os.getenv("OUTPUT_DIR", "data")
    fetch_tdcc_opendata(output_dir)
