#!/usr/bin/env python3
"""
Data Quality Checker for institutional_investors category
"""

from data_quality_checker_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class InstitutionalInvestorsChecker(DataQualityCheckerBase):
    """Checker for institutional_investors - buy/sell/net data"""

    @property
    def category(self):
        return "institutional_investors"

    @property
    def key_columns(self):
        return ['foreign_net', 'trust_net', 'dealer_net']

    @property
    def null_threshold(self):
        return 50.0

    # All numeric columns (integers in raw, floats in processed)
    INTEGER_COLUMNS = {
        'foreign_buy', 'foreign_sell', 'foreign_net',
        'foreign_dealer_buy', 'foreign_dealer_sell', 'foreign_dealer_net',
        'trust_buy', 'trust_sell', 'trust_net',
        'dealer_self_buy', 'dealer_self_sell', 'dealer_self_net',
        'dealer_hedge_buy', 'dealer_hedge_sell', 'dealer_hedge_net',
        'dealer_net', 'total_net',
        'foreign_total_buy', 'foreign_total_sell', 'foreign_total_net',
        'dealer_total_buy', 'dealer_total_sell'
    }

    STRING_COLUMNS = {'symbol', 'name'}

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for institutional_investors"""
        raw_clean = clean_value_for_comparison(raw_val)

        # Handle empty values
        if pd.isna(processed_val) or str(processed_val) in ('', 'nan', 'None', 'NaN'):
            return raw_clean == "" or raw_clean == "--"

        processed_str = str(processed_val)

        # String columns
        if col_name in self.STRING_COLUMNS:
            processed_clean = clean_value_for_comparison(processed_val)
            if processed_clean in raw_clean or raw_clean in processed_clean:
                return True
            return processed_clean == raw_clean

        # Integer columns
        if col_name in self.INTEGER_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return True
                raw_int = int(raw_clean)
                if '.' in processed_str:
                    processed_int = int(float(processed_str))
                else:
                    processed_int = int(processed_str)
                return processed_int == raw_int
            except (ValueError, TypeError):
                pass

        return super()._compare_values(processed_val, raw_val, col_name)
