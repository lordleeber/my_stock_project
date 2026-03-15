#!/usr/bin/env python3
"""
Data Quality Checker for margin_sbl category (Securities Borrowing and Lending)
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class MarginSblChecker(DataQualityCheckerBase):
    """Checker for margin_sbl - securities borrowing and lending data"""

    @property
    def category(self):
        return "margin_sbl"

    @property
    def key_columns(self):
        return ["margin_short_balance", "margin_short_buy", "margin_short_sell"]

    @property
    def null_threshold(self):
        return 90.0

    # Integer columns
    INTEGER_COLUMNS = {
        "margin_short_prev_balance",
        "margin_short_balance",
        "margin_short_buy",
        "margin_short_sell",
        "sbl_prev_balance",
        "sbl_sell",
        "sbl_repay",
        "sbl_balance",
    }

    STRING_COLUMNS = {"symbol", "name"}

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for margin_sbl"""
        raw_clean = clean_value_for_comparison(raw_val)

        # Handle empty values
        if pd.isna(processed_val) or str(processed_val) in ("", "nan", "None", "NaN"):
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
                if "." in processed_str:
                    processed_int = int(float(processed_str))
                else:
                    processed_int = int(processed_str)
                return processed_int == raw_int
            except (ValueError, TypeError):
                pass

        return super()._compare_values(processed_val, raw_val, col_name)
