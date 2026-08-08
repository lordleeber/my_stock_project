"""
通用 ETL 處理進入點 (Integrated with Data Quality Checker)

採用「日期優先」循環：處理完每一天後，立刻執行品質稽核。
路徑規範：僅支援新路徑結構 YYYY/YYYYMMDD。
"""

import os
import sys
import datetime
import re
import glob
from audit_base import DataQualityError
from .audit_daily_quotes import DailyQuotesChecker
from .audit_institutional_investors import InstitutionalInvestorsChecker
from .audit_foreign_holding import ForeignHoldingChecker
from .audit_margin_trading import MarginTradingChecker
from .audit_margin_sbl import MarginSblChecker
from .audit_pe_ratio import PeRatioChecker
from .audit_market_indices import MarketIndicesChecker
from .audit_institutional_summary import InstitutionalSummaryChecker
from .audit_margin_summary import MarginSummaryChecker
from .convert_daily_quotes import process_date as process_daily_quotes_date
from .convert_institutional_investors import (
    process_date as process_institutional_investors_date,
)
from .convert_foreign_holding import process_date as process_foreign_holding_date
from .convert_margin_trading import process_date as process_margin_trading_date
from .convert_margin_sbl import process_date as process_margin_sbl_date
from .convert_pe_ratio import process_date as process_pe_ratio_date
from .convert_market_indices import process_date as process_market_indices_date
from .convert_institutional_summary import (
    process_date as process_institutional_summary_date,
)
from .convert_margin_summary import process_date as process_margin_summary_date
from _error_report import log_processing_error

RAW_DIR = os.getenv("RAW_DIR", "/app/data/raw")
PROCESSED_DIR = os.getenv("PROCESSED_DIR", "/app/data/processed")
FORCE_REPROCESS = os.getenv("FORCE_REPROCESS", "0") == "1"

CATEGORY_PROCESSORS = {
    "daily_quotes": process_daily_quotes_date,
    "institutional_investors": process_institutional_investors_date,
    "foreign_holding": process_foreign_holding_date,
    "margin_trading": process_margin_trading_date,
    "margin_sbl": process_margin_sbl_date,
    "pe_ratio": process_pe_ratio_date,
    "market_indices": process_market_indices_date,
    "institutional_summary": process_institutional_summary_date,
    "margin_summary": process_margin_summary_date,
}

CATEGORY_CHECKERS = {
    "daily_quotes": DailyQuotesChecker,
    "institutional_investors": InstitutionalInvestorsChecker,
    "foreign_holding": ForeignHoldingChecker,
    "margin_trading": MarginTradingChecker,
    "margin_sbl": MarginSblChecker,
    "pe_ratio": PeRatioChecker,
    "market_indices": MarketIndicesChecker,
    "institutional_summary": InstitutionalSummaryChecker,
    "margin_summary": MarginSummaryChecker,
}


def process_date_category(category, date_str):
    if category not in CATEGORY_PROCESSORS:
        return False

    if not should_process_category(category, date_str):
        return False

    CATEGORY_PROCESSORS[category](
        date_str,
        raw_dir=RAW_DIR,
        processed_dir=PROCESSED_DIR,
        force_reprocess=FORCE_REPROCESS,
    )
    return True


def _date_dir(base_dir, category, date_str):
    return os.path.join(base_dir, category, date_str[:4], date_str)


def should_process_category(category, date_str):
    if FORCE_REPROCESS:
        return True

    processed_date_dir = _date_dir(PROCESSED_DIR, category, date_str)

    # Categories that aggregate to a single all.csv
    if category in ("institutional_summary", "margin_summary"):
        output_file = os.path.join(processed_date_dir, "all.csv")
        if os.path.exists(output_file):
            return False

        # margin_summary is derived from raw/margin_trading, not raw/margin_summary.
        raw_source_category = (
            "margin_trading" if category == "margin_summary" else category
        )
        raw_date_dir = _date_dir(RAW_DIR, raw_source_category, date_str)
        return any(glob.glob(os.path.join(raw_date_dir, "*.csv")))

    # market_indices is special:
    # - otc from raw/market_indices/<date>/otc.csv
    # - sii extracted from raw/daily_quotes/<date>/sii.csv
    if category == "market_indices":
        otc_raw = os.path.join(
            _date_dir(RAW_DIR, "market_indices", date_str), "otc.csv"
        )
        sii_raw = os.path.join(_date_dir(RAW_DIR, "daily_quotes", date_str), "sii.csv")
        otc_out = os.path.join(processed_date_dir, "otc.csv")
        sii_out = os.path.join(processed_date_dir, "sii.csv")

        if os.path.exists(otc_raw) and not os.path.exists(otc_out):
            return True
        if os.path.exists(sii_raw) and not os.path.exists(sii_out):
            return True
        return False

    # Generic market categories (sii/otc csv)
    raw_date_dir = _date_dir(RAW_DIR, category, date_str)
    for raw_file in glob.glob(os.path.join(raw_date_dir, "*.csv")):
        output_file = os.path.join(processed_date_dir, os.path.basename(raw_file))
        if not os.path.exists(output_file):
            return True
    return False


def run_category_quality_check(category, date_str):
    checker_class = CATEGORY_CHECKERS.get(category)
    if checker_class is None:
        return

    print(f"Auditing {category} data for {date_str}...")
    try:
        checker = checker_class(date_str)
        checker.check()
        print(f"✅ {category} data quality check passed for {date_str}")
    except DataQualityError as e:
        error_msg = f"{category} data quality check failed: {str(e)}"
        print(f"❌ {error_msg}")
        log_processing_error(error_msg, date_str, category)
        print(
            "❌ Processing stopped due to data quality error. Fix the issue and re-run."
        )
        sys.exit(1)


def main():
    start_env = os.getenv("START_DATE")
    end_env = os.getenv("END_DATE")
    if not start_env or not end_env:
        print("Error: START_DATE and END_DATE are both required (YYYYMMDD).")
        print("Example: START_DATE=20240102 END_DATE=20240102 python convert_daily.py")
        sys.exit(1)

    try:
        start_date = datetime.datetime.strptime(start_env, "%Y%m%d")
        end_date = datetime.datetime.strptime(end_env, "%Y%m%d")
    except ValueError:
        print(
            f"Error: Invalid date format (START_DATE={start_env}, END_DATE={end_env}). Expected YYYYMMDD."
        )
        sys.exit(1)

    if start_date > end_date:
        print(
            f"Error: START_DATE must be <= END_DATE (START_DATE={start_env}, END_DATE={end_env})."
        )
        sys.exit(1)

    print("Starting Unified ETL Pipeline...")

    all_categories = [
        "daily_quotes",
        "institutional_investors",
        "foreign_holding",
        "margin_trading",
        "margin_sbl",
        "pe_ratio",
        "market_indices",
        "institutional_summary",
        "margin_summary",
    ]

    # 1. 搜集所有需要處理的日期 (僅掃描新路徑 YYYY/YYYYMMDD)
    date_pattern = re.compile(r"^\d{8}$")
    all_dates = set()
    for cat in all_categories:
        cat_path = os.path.join(RAW_DIR, cat)
        if os.path.exists(cat_path):
            for d in os.listdir(cat_path):
                if len(d) == 4 and d.isdigit():
                    y_path = os.path.join(cat_path, d)
                    if os.path.isdir(y_path):
                        for sub_d in os.listdir(y_path):
                            if date_pattern.match(sub_d):
                                all_dates.add(sub_d)

    sorted_dates = sorted(list(all_dates))

    # 2. 依照日期順序執行
    for date_str in sorted_dates:
        try:
            curr = datetime.datetime.strptime(date_str, "%Y%m%d")
            # 日期範圍過濾
            if start_date and curr < start_date:
                continue
            if end_date and curr > end_date:
                continue

            # 2a. 處理當天所有類別
            for category in all_categories:
                processed = process_date_category(category, date_str)
                if processed:
                    run_category_quality_check(category, date_str)

        except Exception as e:
            log_processing_error(f"Error in main loop for {date_str}: {e}", date_str)
            sys.exit(1)


if __name__ == "__main__":
    main()
