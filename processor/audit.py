#!/usr/bin/env python3
"""
Data Quality Checker for Processed Data

Checks processed CSV files for data quality issues and writes findings to error_processor.log
Run after processor to catch issues before importing to database.

Usage:
    START_DATE=20260207 END_DATE=20260207 python audit.py

This module coordinates category-specific checkers:
    - daily/audit_daily_quotes.py
    - daily/audit_institutional_investors.py
    - daily/audit_margin_trading.py
    - daily/audit_margin_sbl.py
    - daily/audit_pe_ratio.py
    - daily/audit_foreign_holding.py
    - daily/audit_market_indices.py
    - daily/audit_institutional_summary.py
    - daily/audit_margin_summary.py
    - monthly/audit_monthly_revenue.py
    - weekly/audit_shareholding.py
"""

import os
import sys
from datetime import datetime

from audit_base import DataQualityError
from daily.audit_daily_quotes import DailyQuotesChecker
from daily.audit_institutional_investors import InstitutionalInvestorsChecker
from daily.audit_margin_trading import MarginTradingChecker
from daily.audit_margin_sbl import MarginSblChecker
from daily.audit_pe_ratio import PeRatioChecker
from daily.audit_foreign_holding import ForeignHoldingChecker
from daily.audit_market_indices import MarketIndicesChecker
from daily.audit_institutional_summary import InstitutionalSummaryChecker
from daily.audit_margin_summary import MarginSummaryChecker
from monthly.audit_monthly_revenue import MonthlyRevenueChecker
from weekly.audit_shareholding import ShareholdingChecker


def main():
    """Main entry point for data quality checking"""
    # Get date range from environment variable
    date_str = os.getenv('START_DATE')
    end_date_str = os.getenv('END_DATE')

    if not date_str or not end_date_str:
        print("Error: START_DATE and END_DATE are both required (YYYYMMDD).")
        print("Usage: START_DATE=20260207 END_DATE=20260207 python audit.py")
        sys.exit(1)

    # Validate date format
    try:
        datetime.strptime(date_str, '%Y%m%d')
        datetime.strptime(end_date_str, '%Y%m%d')
    except ValueError:
        print(f"Error: Invalid date format (START_DATE={date_str}, END_DATE={end_date_str}). Expected YYYYMMDD.")
        sys.exit(1)

    if date_str != end_date_str:
        print(f"Error: audit.py only supports a single date; require START_DATE == END_DATE (got {date_str} ~ {end_date_str}).")
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
