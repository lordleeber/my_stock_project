#!/usr/bin/env python3
"""
Data Quality Checker for margin_trading category
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class MarginTradingChecker(DataQualityCheckerBase):
    """Checker for margin_trading - margin long/short data"""

    @property
    def category(self):
        return "margin_trading"

    @property
    def key_columns(self):
        return [
            'margin_long_buy',
            'margin_long_sell',
            'margin_long_balance',
            'margin_short_buy',
            'margin_short_sell',
            'margin_short_balance'
        ]

    @property
    def null_threshold(self):
        return 90.0  # Margin trading has more legitimately NULL values

    # All margin trading numeric columns
    INTEGER_COLUMNS = {
        'margin_long_buy', 'margin_long_sell', 'margin_long_cash_repay',
        'margin_long_prev_balance', 'margin_long_balance', 'margin_long_limit',
        'margin_short_buy', 'margin_short_sell', 'margin_short_cash_repay',
        'margin_short_prev_balance', 'margin_short_balance', 'margin_short_limit',
        'offset_balance'
    }

    FLOAT_COLUMNS = {'margin_long_utilization', 'margin_short_utilization'}

    STRING_COLUMNS = {'symbol', 'name'}

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for margin_trading"""
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

        # Float columns
        if col_name in self.FLOAT_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return True
                raw_float = float(raw_clean)
                processed_float = float(processed_str)
                return abs(processed_float - raw_float) < 0.0001
            except (ValueError, TypeError):
                pass

        return super()._compare_values(processed_val, raw_val, col_name)
