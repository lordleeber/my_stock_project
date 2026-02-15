#!/usr/bin/env python3
"""
Data Quality Checker for daily_quotes category
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class DailyQuotesChecker(DataQualityCheckerBase):
    """Checker for daily_quotes - OHLCV data with numeric columns"""

    @property
    def category(self):
        return "daily_quotes"

    @property
    def key_columns(self):
        return ['open', 'high', 'low', 'close', 'volume']

    @property
    def null_threshold(self):
        return 50.0

    # Columns that are integers in raw but floats in processed
    INTEGER_COLUMNS = {'volume', 'transactions', 'value'}

    # Columns that are floats
    FLOAT_COLUMNS = {'open', 'high', 'low', 'close', 'change', 'bid', 'ask'}

    # String columns
    STRING_COLUMNS = {'symbol', 'name', 'direction'}

    def _check_category_specific(self, df, market):
        """Check OHLC logic consistency"""
        # OHLC logic check: High must be highest, Low must be lowest
        ohlc_err = df[
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        ]
        if len(ohlc_err) > 0:
            self._raise_error(
                f"daily_quotes {market}: Found {len(ohlc_err)} rows with invalid OHLC logic "
                f"(e.g., high < close). This strongly suggests column shifting in raw CSV."
            )

    def _compare_values(self, processed_val, raw_val, col_name):
        """
        Custom comparison logic for daily_quotes:
        - Integer columns (volume, transactions, value): convert float to int
        - Float columns (open, high, low, close): compare as floats
        - String columns: direct string comparison
        """
        raw_clean = clean_value_for_comparison(raw_val)

        # Handle empty values
        if pd.isna(processed_val) or str(processed_val) in ('', 'nan', 'None', 'NaN'):
            return raw_clean == "" or raw_clean == "--"

        processed_str = str(processed_val)

        # String columns: direct comparison
        if col_name in self.STRING_COLUMNS:
            processed_clean = clean_value_for_comparison(processed_val)
            # Handle symbol format like ="0050"
            if processed_clean in raw_clean or raw_clean in processed_clean:
                return True
            return processed_clean == raw_clean

        # Integer columns: convert float to int
        if col_name in self.INTEGER_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return True  # Both are effectively empty
                raw_int = int(raw_clean)
                if '.' in processed_str:
                    processed_int = int(float(processed_str))
                else:
                    processed_int = int(processed_str)
                return processed_int == raw_int
            except (ValueError, TypeError):
                pass

        # Float columns: compare as floats with tolerance
        if col_name in self.FLOAT_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return pd.isna(processed_val) or processed_str in ('', 'nan', 'None')
                raw_float = float(raw_clean)
                processed_float = float(processed_str)
                return abs(processed_float - raw_float) < 0.0001
            except (ValueError, TypeError):
                pass

        # Default: use base class comparison
        return super()._compare_values(processed_val, raw_val, col_name)
