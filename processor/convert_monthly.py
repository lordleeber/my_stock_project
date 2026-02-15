from convert_stock_info import process_stock_info
from convert_stock_tags import process_stock_tags
from monthly.convert_monthly_revenue import process_monthly_revenue

if __name__ == '__main__':
    process_stock_info()
    process_stock_tags()
    process_monthly_revenue()
