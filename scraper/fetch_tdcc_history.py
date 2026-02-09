import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os
import random
import logging

# 設定 Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"

URL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Origin': 'https://www.tdcc.com.tw',
    'Referer': URL
}

class TDCCScraper:
    def __init__(self, verify_ssl=True):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.verify = verify_ssl
        self.current_token = None
        self.current_uri = None
        self.current_fir_date = None
        self.available_dates = []

    def initialize(self):
        """Fetch initial page to get token and available dates."""
        logger.info("Initializing session and fetching valid dates...")
        try:
            resp = self.session.get(URL, timeout=30)
            resp.raise_for_status()
            self._parse_page(resp.text)
            
            # Parse dates from the select option
            soup = BeautifulSoup(resp.text, 'html.parser')
            date_select = soup.find('select', {'id': 'scaDate'})
            if date_select:
                self.available_dates = [option['value'] for option in date_select.find_all('option')]
                logger.info(f"Found {len(self.available_dates)} available dates. Latest: {self.available_dates[0]}")
            else:
                logger.warning("Could not find date select options.")
                
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            return False

    def _parse_page(self, html_content):
        """Extract hidden fields (Token) from the page."""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        token_tag = soup.find('input', {'name': 'SYNCHRONIZER_TOKEN'})
        uri_tag = soup.find('input', {'name': 'SYNCHRONIZER_URI'})
        fir_date_tag = soup.find('input', {'name': 'firDate'})
        
        if token_tag:
            self.current_token = token_tag['value']
        if uri_tag:
            self.current_uri = uri_tag['value']
        if fir_date_tag:
            self.current_fir_date = fir_date_tag['value']

    def scrape_stock(self, stock_no, date_str):
        """
        Query data for a specific stock and date.
        Returns a DataFrame if successful, None otherwise.
        """
        if not self.current_token:
            logger.error("No token available. Run initialize() first.")
            return None

        # Prepare payload
        payload = {
            'SYNCHRONIZER_TOKEN': self.current_token,
            'SYNCHRONIZER_URI': self.current_uri if self.current_uri else '/portal/zh/smWeb/qryStock',
            'method': 'submit',
            'firDate': self.current_fir_date if self.current_fir_date else '',
            'scaDate': date_str,
            'sqlMethod': 'StockNo',
            'stockNo': stock_no,
            'stockName': ''
        }

        try:
            time.sleep(random.uniform(1.0, 2.0)) # Polite delay
            
            resp = self.session.post(URL, data=payload, timeout=30)
            resp.raise_for_status()
            
            # Important: Update token for the next request from the response!
            self._parse_page(resp.text)
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Find the result table
            # The result table usually has class 'table' and contains specific headers
            tables = soup.find_all('table', {'class': 'table'})
            
            target_table = None
            for tbl in tables:
                headers = [th.text.strip() for th in tbl.find_all('th')]
                if "持股/單位數分級" in headers or "人數" in headers:
                    target_table = tbl
                    break
            
            if not target_table:
                # Check for error message in page
                if "查無資料" in resp.text:
                    logger.warning(f"No data found for {stock_no} on {date_str}")
                else:
                    # Sometimes the table index might be different or page structure changed slightly
                    # But if we updated the token, we can at least continue.
                    pass
                return None

            # Parse Table to DataFrame
            rows = []
            # The table body
            tbody = target_table.find('tbody')
            tr_elements = tbody.find_all('tr') if tbody else target_table.find_all('tr')
            
            for tr in tr_elements:
                tds = tr.find_all('td')
                if not tds:
                    continue # Skip header row if mixed in
                row_data = [td.text.strip() for td in tds]
                if len(row_data) >= 5: # Ensure we have enough columns
                    rows.append(row_data)

            if not rows:
                return None

            # Define columns based on standard TDCC format
            columns = ['序', '持股分級', '人數', '股數', '占集保庫存數比例(%)']
            # Sometimes row might have more or fewer cols? Standardize to first 5
            cleaned_rows = [r[:5] for r in rows]
            
            df = pd.DataFrame(cleaned_rows, columns=columns)
            return df

        except Exception as e:
            logger.error(f"Error scraping {stock_no}: {e}")
            return None

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch TDCC Shareholding Dispersion History")
    parser.add_argument("--stock", "-s", type=str, help="Single stock ID to fetch")
    parser.add_argument("--file", "-f", type=str, help="File containing list of stock IDs (one per line)")
    parser.add_argument("--date", "-d", type=str, help="Date to fetch (YYYYMMDD) or file containing list of dates")
    parser.add_argument("--output", "-o", type=str, default="data/raw/shareholding_div", help="Output directory")
    parser.add_argument("--list-dates", action="store_true", help="List all available dates from TDCC website")
    parser.add_argument("--no-verify", action="store_true", help="Disable SSL certificate verification")

    args = parser.parse_args()

    if args.no_verify:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    scraper = TDCCScraper(verify_ssl=not args.no_verify)
    if not scraper.initialize():
        return

    if args.list_dates:
        print(f"Available Dates ({len(scraper.available_dates)}):")
        print(scraper.available_dates)
        return

    if not args.date:
        logger.error("Please provide --date or --list-dates")
        return

    # Determine date list
    date_list = []
    if os.path.exists(args.date):
        logger.info(f"Reading dates from file: {args.date}")
        with open(args.date, 'r', encoding='utf-8') as f:
            date_list = [line.strip() for line in f if line.strip()]
    else:
        date_list = [args.date]

    stock_list = []
    if args.stock:
        stock_list.append(args.stock)
    elif args.file:
        if os.path.exists(args.file):
            with open(args.file, 'r', encoding='utf-8') as f:
                stock_list = [line.strip() for line in f if line.strip()]
        else:
            logger.error(f"File not found: {args.file}")
            return
    else:
        logger.error("Please provide --stock or --file")
        return

    logger.info(f"Target: {len(stock_list)} stocks, Dates: {len(date_list)}")

    for date_str in date_list:
        logger.info(f"Processing date: {date_str}")
        
        # Check date validity
        if date_str not in scraper.available_dates:
            logger.warning(f"Date {date_str} might not be available. Available dates (top 5): {scraper.available_dates[:5]}")
        
        # Prepare output dir
        output_dir = os.path.join(args.output, f"date={date_str}")
        os.makedirs(output_dir, exist_ok=True)

        for idx, stock_id in enumerate(stock_list):
            output_path = os.path.join(output_dir, f"{stock_id}.csv")
            
            if os.path.exists(output_path):
                if FORCE_REPROCESS:
                    logger.info(f"[{idx+1}/{len(stock_list)}] {stock_id} exists for {date_str}, reprocessing due to FORCE_REPROCESS=1.")
                else:
                    logger.info(f"[{idx+1}/{len(stock_list)}] {stock_id} already exists for {date_str}. Skipping.")
                    continue

            logger.info(f"[{idx+1}/{len(stock_list)}] Fetching {stock_id} for {date_str}...")
            df = scraper.scrape_stock(stock_id, date_str)
            
            if df is not None and not df.empty:
                df.to_csv(output_path, index=False, encoding='utf-8-sig')
                logger.info(f"Saved {stock_id}.csv ({len(df)} rows)")
            else:
                logger.warning(f"Failed to fetch or empty data for {stock_id} on {date_str}")
            
        # Optional: Save checkpoint or retry logic could be added here

if __name__ == "__main__":
    main()
