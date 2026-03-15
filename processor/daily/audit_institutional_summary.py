#!/usr/bin/env python3
"""
Data Quality Checker for institutional_summary category
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


# Institution name mapping (Chinese -> English, matching convert_daily.py)
INSTITUTION_MAP = {
    "自營商(自行買賣)": "dealer_self",
    "自營商(避險)": "dealer_hedge",
    "投信": "investment_trust",
    "外資及陸資(不含外資自營商)": "foreign_investors",
    "外資自營商": "foreign_dealer",
    "合計": "total",
    "自營商(自行買賣)\u3000": "dealer_self",
    "自營商(避險)\u3000": "dealer_hedge",
    "外資及陸資(不含自營商)": "foreign_investors",
    "外資及陸資合計": "foreign_total",
    "自營商合計": "dealer_total",
    "三大法人合計*": "total",
    "三大法人合計": "total",
}


class InstitutionalSummaryChecker(DataQualityCheckerBase):
    """Checker for institutional_summary - aggregate institutional data"""

    @property
    def category(self):
        return "institutional_summary"

    @property
    def markets(self):
        return [None]  # Uses all.csv, no market split

    @property
    def key_columns(self):
        return ["buy", "sell", "net"]

    @property
    def null_threshold(self):
        return 10.0  # Summary should have no NULL

    INTEGER_COLUMNS = {"buy", "sell", "net"}
    STRING_COLUMNS = {"institution"}

    # Columns that undergo transformation (Chinese -> English mapping)
    TRANSFORMED_COLUMNS = {"institution"}

    def _check_category_specific(self, df, market):
        """Check that we have data for major institution types"""
        if "institution" in df.columns:
            institutions = df["institution"].unique()
            expected_institutions = ["foreign", "trust", "dealer"]

            for inst in expected_institutions:
                if not any(inst in str(i).lower() for i in institutions):
                    self._raise_error(
                        f"institutional_summary: Missing expected institution type '{inst}'"
                    )

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for institutional_summary"""
        raw_clean = clean_value_for_comparison(raw_val)

        # Handle empty values
        if pd.isna(processed_val) or str(processed_val) in ("", "nan", "None", "NaN"):
            return raw_clean == "" or raw_clean == "--"

        processed_str = str(processed_val)

        # Transformed columns (Chinese -> English mapping)
        if col_name in self.TRANSFORMED_COLUMNS:
            # Check if raw value maps to processed value
            expected_eng = INSTITUTION_MAP.get(raw_clean.strip())
            if expected_eng:
                return processed_str.strip() == expected_eng
            # If not in map, try direct comparison
            processed_clean = clean_value_for_comparison(processed_val)
            return processed_clean in raw_clean or raw_clean in processed_clean

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

    def get_file_path(self, market=None):
        """Override to always use all.csv"""
        from audit_base import get_processed_date_path

        return get_processed_date_path(self.category, self.date_str)
