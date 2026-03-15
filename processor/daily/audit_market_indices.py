#!/usr/bin/env python3
"""
Data Quality Checker for market_indices category
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class MarketIndicesChecker(DataQualityCheckerBase):
    """Checker for market_indices - market index data"""

    @property
    def category(self):
        return "market_indices"

    @property
    def key_columns(self):
        return ["index_close", "index_change_points"]

    @property
    def null_threshold(self):
        return 30.0  # Market indices should have very low NULL rate

    FLOAT_COLUMNS = {"index_close", "index_change_points"}
    STRING_COLUMNS = {"symbol", "index_name"}

    def _handle_missing_file(self, file_path, market):
        """SII market indices might be missing if extraction failed"""
        if market == "sii":
            # SII is extracted from daily_quotes, might not exist
            return
        # OTC should always exist
        self._raise_error(f"{self.category}: Missing file {file_path}")

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for market_indices"""
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
