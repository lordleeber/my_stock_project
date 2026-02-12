#!/usr/bin/env python3
"""
Data Quality Checker for shareholding category
"""

from data_quality_checker_base import DataQualityCheckerBase, clean_value_for_comparison, get_processed_date_path
from pathlib import Path
import pandas as pd


class ShareholdingChecker(DataQualityCheckerBase):
    """Checker for shareholding - TDCC shareholding dispersion data"""

    @property
    def category(self):
        return "shareholding"

    @property
    def markets(self):
        return [None]  # Single file per date, no sii/otc split

    @property
    def key_columns(self):
        return ['holders', 'shares', 'percentage']

    # Integer columns
    INTEGER_COLUMNS = {'level', 'holders', 'shares'}

    # Float columns
    FLOAT_COLUMNS = {'percentage'}

    # String columns
    STRING_COLUMNS = {'symbol', 'level_name'}

    def get_file_path(self, market=None):
        """Override: shareholding uses YYYY/YYYYMMDD.csv path"""
        year = self.date_str[:4]

        # Check new path structure: YYYY/YYYYMMDD.csv
        new_path = Path(f"data/processed/{self.category}/{year}/{self.date_str}.csv")
        if new_path.exists():
            return new_path

        # Fallback to old structure: date=YYYYMMDD/all.csv
        old_path = Path(f"data/processed/{self.category}/date={self.date_str}/all.csv")
        return old_path

    def _handle_missing_file(self, file_path, market):
        """Shareholding is weekly (Fridays only) - skip silently if file missing"""
        pass

    def check(self):
        """Override check to handle single file without market loop"""
        print(f"Checking {self.category}...")

        file_path = self.get_file_path()

        if not file_path.exists():
            # Shareholding is weekly, skip silently
            return

        try:
            df = pd.read_csv(file_path)

            if len(df) == 0:
                self._raise_error(f"{self.category}: File is empty (0 rows)")

            # Run standard key column checks
            self._check_key_columns(df, None)

            # Run category-specific checks
            self._check_category_specific(df, None)

            # Run lineage verification
            self._verify_lineage(df, None)

        except Exception as e:
            if "DataQualityError" in type(e).__name__:
                raise
            self._raise_error(f"{self.category}: Error reading file - {str(e)}")

    def _check_category_specific(self, df, market):
        """Verify shareholding-specific constraints"""
        # Verify level values are 1-15
        if 'level' in df.columns:
            invalid_levels = df[~df['level'].isin(range(1, 16))]
            if len(invalid_levels) > 0:
                self._raise_error(
                    f"{self.category}: Found {len(invalid_levels)} rows with invalid level values "
                    f"(expected 1-15, got: {sorted(invalid_levels['level'].unique().tolist())})"
                )

        # Verify each symbol has exactly 15 level rows
        if 'symbol' in df.columns and 'level' in df.columns:
            level_counts = df.groupby('symbol')['level'].count()
            bad_symbols = level_counts[level_counts != 15]
            if len(bad_symbols) > 0:
                examples = bad_symbols.head(5).to_dict()
                self._raise_error(
                    f"{self.category}: {len(bad_symbols)} symbols don't have exactly 15 levels. "
                    f"Examples: {examples}"
                )

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
        """Custom comparison for shareholding"""
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

        # Integer columns (level, holders, shares)
        if col_name in self.INTEGER_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return True
                raw_int = int(float(raw_clean))
                if '.' in processed_str:
                    processed_int = int(float(processed_str))
                else:
                    processed_int = int(processed_str)
                return processed_int == raw_int
            except (ValueError, TypeError):
                pass

        # Float columns (percentage)
        if col_name in self.FLOAT_COLUMNS:
            try:
                if raw_clean == "" or raw_clean == "--":
                    return True
                raw_float = float(raw_clean)
                processed_float = float(processed_str)
                return abs(processed_float - raw_float) < 0.01
            except (ValueError, TypeError):
                pass

        return super()._compare_values(processed_val, raw_val, col_name)
