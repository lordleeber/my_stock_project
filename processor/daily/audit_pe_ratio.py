#!/usr/bin/env python3
"""
Data Quality Checker for pe_ratio category
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class PeRatioChecker(DataQualityCheckerBase):
    """Checker for pe_ratio data"""

    @property
    def category(self):
        return "pe_ratio"

    @property
    def key_columns(self):
        return ["pe_ratio"]

    @property
    def null_threshold(self):
        return 80.0  # PE ratio can legitimately be NULL for many stocks

    FLOAT_COLUMNS = {"pe_ratio"}
    STRING_COLUMNS = {"symbol", "name"}

    def _check_category_specific(self, df, market):
        """Check for negative PE ratios"""
        if "pe_ratio" in df.columns:
            invalid_count = (df["pe_ratio"] < 0).sum()
            if invalid_count > 0:
                self._raise_error(
                    f"pe_ratio {market}: Found {invalid_count} negative PE ratio values "
                    "(PE ratio should be positive or NULL)"
                )

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for pe_ratio"""
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
