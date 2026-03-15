#!/usr/bin/env python3
"""
Data Quality Checker for foreign_holding category
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class ForeignHoldingChecker(DataQualityCheckerBase):
    """Checker for foreign_holding - foreign shareholding data"""

    @property
    def category(self):
        return "foreign_holding"

    @property
    def key_columns(self):
        return [
            "foreign_held_shares",
            "foreign_investable_shares",
            "foreign_held_ratio",
        ]

    @property
    def null_threshold(self):
        return 70.0

    # Integer columns (shares)
    INTEGER_COLUMNS = {
        "issued_shares",
        "foreign_investable_shares",
        "foreign_held_shares",
    }

    # Float columns (ratios)
    FLOAT_COLUMNS = {
        "foreign_investable_ratio",
        "foreign_held_ratio",
        "foreign_legal_limit_ratio",
    }

    STRING_COLUMNS = {"symbol", "name"}

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for foreign_holding"""
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
