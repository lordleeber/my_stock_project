#!/usr/bin/env python3
"""
Data Quality Checker for Processed Data

Checks processed CSV files for data quality issues and writes findings to error_processor.md
Run after processor to catch issues before importing to database.

Usage:
    python data_quality_checker.py YYYYMMDD
    START_DATE=20260207 python data_quality_checker.py

This module coordinates category-specific checkers:
    - data_quality_checker_daily_quotes.py
    - data_quality_checker_institutional_investors.py
    - data_quality_checker_margin_trading.py
    - data_quality_checker_margin_sbl.py
    - data_quality_checker_pe_ratio.py
    - data_quality_checker_foreign_holding.py
    - data_quality_checker_market_indices.py
    - data_quality_checker_institutional_summary.py
    - data_quality_checker_margin_summary.py
    - data_quality_checker_shareholding.py
"""

import os
import sys
from datetime import datetime

from data_quality_checker_base import DataQualityError
from data_quality_checker_daily_quotes import DailyQuotesChecker
from data_quality_checker_institutional_investors import InstitutionalInvestorsChecker
from data_quality_checker_margin_trading import MarginTradingChecker
from data_quality_checker_margin_sbl import MarginSblChecker
from data_quality_checker_pe_ratio import PeRatioChecker
from data_quality_checker_foreign_holding import ForeignHoldingChecker
from data_quality_checker_market_indices import MarketIndicesChecker
from data_quality_checker_institutional_summary import InstitutionalSummaryChecker
from data_quality_checker_margin_summary import MarginSummaryChecker
from data_quality_checker_monthly_revenue import MonthlyRevenueChecker
from data_quality_checker_shareholding import ShareholdingChecker


def main():
    """Main entry point for data quality checking"""
    # Get date from environment variable or command line
    date_str = os.getenv('START_DATE')

    if not date_str and len(sys.argv) > 1:
        date_str = sys.argv[1]

    if not date_str:
        print("Error: Please provide date via START_DATE env var or command line argument")
        print("Usage: python data_quality_checker.py YYYYMMDD")
        print("   or: START_DATE=20260207 python data_quality_checker.py")
        sys.exit(1)

    # Validate date format
    try:
        datetime.strptime(date_str, '%Y%m%d')
    except ValueError:
        print(f"Error: Invalid date format '{date_str}'. Expected YYYYMMDD")
        sys.exit(1)

    print(f"🔍 Checking data quality for {date_str}...")
    print(f"📂 Processed data directory: data/processed/")
    print()

    # List of all checkers to run
    checkers = [
        MarginTradingChecker,
        MarginSblChecker,
        DailyQuotesChecker,
        InstitutionalInvestorsChecker,
        ForeignHoldingChecker,
        PeRatioChecker,
        MarketIndicesChecker,
        InstitutionalSummaryChecker,
        MarginSummaryChecker,
        MonthlyRevenueChecker,
        ShareholdingChecker,
    ]

    try:
        for checker_class in checkers:
            checker = checker_class(date_str)
            checker.check()

        print("\n✅ All data quality checks passed!")
        sys.exit(0)

    except DataQualityError as e:
        print(f"\n❌ Data quality check FAILED")
        print(f"   Processing stopped due to error.")
        sys.exit(1)


if __name__ == '__main__':
    main()
