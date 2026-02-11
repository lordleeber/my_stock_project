#!/usr/bin/env python3
"""
Data Quality Checker for margin_summary category
"""

from data_quality_checker_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class MarginSummaryChecker(DataQualityCheckerBase):
    """Checker for margin_summary - aggregate margin data

    Note: margin_summary is constructed from parsing specific rows in raw files.
    The 'item' column is assigned during processing, not directly from raw.
    """

    @property
    def category(self):
        return "margin_summary"

    @property
    def markets(self):
        return [None]  # Uses all.csv, no market split

    @property
    def key_columns(self):
        return ['buy', 'sell', 'today_balance']

    @property
    def null_threshold(self):
        return 10.0

    INTEGER_COLUMNS = {'buy', 'sell', 'cash_repay', 'prev_balance', 'today_balance'}
    STRING_COLUMNS = {'item'}

    # Columns that are assigned during processing (not direct copies from raw)
    TRANSFORMED_COLUMNS = {'item'}

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for margin_summary"""
        raw_clean = clean_value_for_comparison(raw_val)

        # Handle empty values
        if pd.isna(processed_val) or str(processed_val) in ('', 'nan', 'None', 'NaN'):
            return raw_clean == "" or raw_clean == "--"

        processed_str = str(processed_val)

        # Transformed columns are derived during processing, skip direct comparison
        if col_name in self.TRANSFORMED_COLUMNS:
            # The 'item' column is assigned based on parsing, not from a direct raw column
            # Just check that it's a valid item name
            valid_items = {'融資', '融券', '融資(交易單位)', '融券(交易單位)', '融資金額(仟元)'}
            return any(v in processed_str for v in valid_items) or processed_str in raw_clean

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

    def get_file_path(self, market=None):
        """Override to always use all.csv"""
        from data_quality_checker_base import get_processed_date_path
        return get_processed_date_path(self.category, self.date_str)
