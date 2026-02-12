#!/usr/bin/env python3
"""
Data Quality Checker for monthly_revenue category
"""

from data_quality_checker_base import DataQualityCheckerBase, clean_value_for_comparison, get_processed_date_path
from pathlib import Path
import pandas as pd
import re


class MonthlyRevenueChecker(DataQualityCheckerBase):
    """Checker for monthly_revenue - company revenue data"""

    @property
    def category(self):
        return "monthly_revenue"

    @property
    def markets(self):
        return [None]  # Uses all.csv, no market split

    @property
    def key_columns(self):
        return ['revenue_current', 'mom_pct', 'yoy_pct']

    @property
    def null_threshold(self):
        return 60.0  # Revenue data can have some NULL

    # Integer columns (raw integers, processed as floats)
    INTEGER_COLUMNS = {
        'revenue_current', 'revenue_last_month', 'revenue_last_year',
        'revenue_cumulative', 'revenue_cumulative_last_year'
    }

    # Float columns (percentages)
    FLOAT_COLUMNS = {'mom_pct', 'yoy_pct', 'cumulative_yoy_pct'}

    # String columns
    STRING_COLUMNS = {'symbol', 'name', 'comment', 'market'}

    def get_file_path(self, market=None):
        """Override to handle monthly_revenue date format (YYYYMXX)"""
        # Convert YYYYMMDD to YYYYMXX
        year = self.date_str[:4]
        month = self.date_str[4:6]
        ym_str = f"{year}M{month}"

        # Check new path structure first: YYYY/YYYYMXX/all.csv
        new_path = Path(f"data/processed/{self.category}/{year}/{ym_str}/all.csv")
        if new_path.exists():
            return new_path

        # Fallback to old structure: date=YYYYMXX/all.csv
        old_path = Path(f"data/processed/{self.category}/date={ym_str}/all.csv")
        return old_path

    def _handle_missing_file(self, file_path, market):
        """Monthly revenue is optional - only available after 10th of each month"""
        # Don't raise error if file doesn't exist
        pass

    def check(self):
        """Override check to handle the case where file doesn't exist"""
        print(f"Checking {self.category}...")

        file_path = self.get_file_path()

        if not file_path.exists():
            # Monthly revenue is optional, skip silently
            return

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                self._raise_error(f"{self.category}: File is empty (0 rows)")

            # Check date format (should be YYYYMXX)
            if 'date' in df.columns:
                invalid_dates = df[~df['date'].astype(str).str.match(r'^\d{4}M\d{2}$')]
                if len(invalid_dates) > 0:
                    self._raise_error(
                        f"{self.category}: Found {len(invalid_dates)} rows with invalid date format "
                        f"(expected YYYYMXX, e.g., 2025M01)"
                    )

            # Run standard key column checks
            self._check_key_columns(df, None)

            # Run lineage verification
            self._verify_lineage(df, None)

        except Exception as e:
            if "DataQualityError" in type(e).__name__:
                raise
            self._raise_error(f"{self.category}: Error reading file - {str(e)}")

    def _verify_lineage(self, df, market):
        """Override to use category label without market"""
        label = self.category

        from data_quality_checker_base import parse_csv_line, DEBUG

        # Check lineage columns exist
        for col in ["src_file", "src_row", "src_col"]:
            if col not in df.columns:
                self._raise_error(f"{label}: Missing lineage column '{col}'")
            if df[col].isna().any():
                self._raise_error(f"{label}: Found NULL values in lineage column '{col}'")

        # Get schema columns (exclude lineage columns)
        schema_cols = [c for c in df.columns if c not in ('src_file', 'src_row', 'src_col')]

        # Verify each row
        from data_quality_checker_base import parse_csv_line, DEBUG

        for idx, row in df.iterrows():
            src_file = str(row['src_file'])
            src_col = str(row['src_col'])

            try:
                src_row = int(float(row['src_row']))
            except (ValueError, TypeError):
                self._raise_error(f"{label} row {idx}: Invalid src_row value '{row['src_row']}'")

            # Resolve file path
            full_path = self._resolve_file_path(src_file, label, idx)
            if full_path is None:
                continue

            # Read raw file (with caching)
            raw_lines = self._read_raw_file(full_path, label, idx)
            if raw_lines is None:
                continue

            # Check src_row exists
            if src_row < 1 or src_row > len(raw_lines):
                self._raise_error(
                    f"{label} row {idx}: Row {src_row} does not exist in source "
                    f"{full_path.name} (has {len(raw_lines)} lines)"
                )

            raw_line = raw_lines[src_row - 1]
            raw_fields = parse_csv_line(raw_line)

            # Parse src_col indices
            col_indices = src_col.split('#')

            if len(col_indices) != len(schema_cols):
                self._raise_error(
                    f"{label} row {idx}: src_col length ({len(col_indices)}) != "
                    f"schema_cols length ({len(schema_cols)})"
                )

            # Verify ALL columns
            for col_idx, (col_name, src_idx_str) in enumerate(zip(schema_cols, col_indices)):
                # Skip processing-added columns (x)
                if src_idx_str == 'x':
                    continue

                try:
                    src_idx = int(src_idx_str) - 1  # Convert to 0-based
                except ValueError:
                    self._raise_error(
                        f"{label} row {idx} col '{col_name}': Invalid src_col index '{src_idx_str}'"
                    )

                if src_idx >= len(raw_fields):
                    self._raise_error(
                        f"{label} row {idx} col '{col_name}': src_col index {src_idx + 1} "
                        f"out of range (raw has {len(raw_fields)} fields)"
                    )

                # Get values for comparison
                processed_val = row.get(col_name, '')
                raw_val = raw_fields[src_idx]

                # Compare values using category-specific logic
                if not self._compare_values(processed_val, raw_val, col_name):
                    self._raise_error(
                        f"{label} row {idx} col '{col_name}': Value mismatch! "
                        f"Processed='{processed_val}', Raw[{src_idx + 1}]='{raw_val}'"
                    )

            if DEBUG and idx % 100 == 0:
                print(f"    Verified {idx + 1}/{len(df)} rows...")

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for monthly_revenue"""
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

        # Integer columns (revenue values)
        if col_name in self.INTEGER_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return True
                # Handle parentheses for negative numbers: (123) -> -123
                if raw_clean.startswith("(") and raw_clean.endswith(")"):
                    raw_clean = "-" + raw_clean[1:-1]
                raw_int = int(float(raw_clean))
                if '.' in processed_str:
                    processed_int = int(float(processed_str))
                else:
                    processed_int = int(processed_str)
                return processed_int == raw_int
            except (ValueError, TypeError):
                pass

        # Float columns (percentages)
        if col_name in self.FLOAT_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return True
                # Handle parentheses for negative numbers
                if raw_clean.startswith("(") and raw_clean.endswith(")"):
                    raw_clean = "-" + raw_clean[1:-1]
                raw_float = float(raw_clean)
                processed_float = float(processed_str)
                return abs(processed_float - raw_float) < 0.01  # 0.01% tolerance for percentages
            except (ValueError, TypeError):
                pass

        return super()._compare_values(processed_val, raw_val, col_name)
