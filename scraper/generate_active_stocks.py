import os
import sys
import argparse
from datetime import datetime
import pandas as pd
import logging
# Add parent directory to path to allow importing fetch_monthly_revenue
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from fetch_monthly_revenue import fetch_market_revenue

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def generate_stock_list(output_file="active_stocks.txt"):
    """
    Generates a list of active stocks by fetching the latest monthly revenue data.
    Filters for 4-digit stock codes to exclude warrants/ETFs if they appear in this specific report
    (though monthly revenue usually only contains companies).
    """
    
    # Determine the target month (last month)
    today = datetime.now()
    if today.month == 1:
        target_year = today.year - 1
        target_month = 12
    else:
        target_year = today.year
        target_month = today.month - 1
        
    year_roc = target_year - 1911
    
    logger.info(f"Targeting revenue report for: {target_year}/{target_month} (ROC {year_roc}/{target_month})")
    
    # Fetch data
    # Note: fetch_market_revenue returns a DataFrame with '公司代號', '公司名稱' etc.
    df_sii = fetch_market_revenue(year_roc, target_month, 'sii')
    df_otc = fetch_market_revenue(year_roc, target_month, 'otc')
    
    all_codes = set()
    
    for market_name, df in [('SII', df_sii), ('OTC', df_otc)]:
        if df is not None and not df.empty:
            # Column name is typically '公司代號' from the fetcher
            if '公司代號' in df.columns:
                codes = df['公司代號'].astype(str).tolist()
                logger.info(f"Fetched {len(codes)} raw codes from {market_name}")
                
                # Filter logic
                for code in codes:
                    code = code.strip()
                    # Basic filter: 4 digits implies common stock. 
                    # ETFs are usually 5 digits or start with 00. 
                    # Warrants are 6 digits.
                    # We strictly keep only 4-digit numeric codes.
                    if len(code) == 4 and code.isdigit():
                         all_codes.add(code)
            else:
                logger.warning(f"Column '公司代號' not found in {market_name} dataframe.")
        else:
            logger.warning(f"No data fetched for {market_name}")

    if not all_codes:
        logger.error("No valid stock codes found. Aborting.")
        return False

    # Sort and Save
    sorted_codes = sorted(list(all_codes))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for code in sorted_codes:
            f.write(f"{code}\n")
            
    logger.info(f"Successfully saved {len(sorted_codes)} active stocks to {output_file}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate active stock list from Monthly Revenue")
    parser.add_argument("--output", "-o", default="active_stocks.txt", help="Output file path")
    args = parser.parse_args()
    
    generate_stock_list(args.output)
