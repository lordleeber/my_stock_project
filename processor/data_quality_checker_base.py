#!/usr/bin/env python3
"""
Base class for Data Quality Checkers

Provides common functionality for all category-specific checkers.
"""

import os
import sys
import csv
import pandas as pd
from datetime import datetime
from pathlib import Path
from abc import ABC, abstractmethod

DEBUG = os.getenv("DEBUG", "0") == "1"


class DataQualityError(Exception):
    """Custom exception for data quality errors that should stop processing"""
    pass


def parse_csv_line(line):
    """Parse a CSV line handling quoted fields with commas."""
    try:
        reader = csv.reader([line])
        return next(reader)
    except Exception:
        return line.strip().split(',')


def clean_value_for_comparison(val):
    """Clean a value for comparison: remove quotes, whitespace, commas in numbers."""
    if val is None:
        return ""
    s = str(val).strip()
    # Remove surrounding quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    # Remove commas (number formatting)
    s = s.replace(',', '')
    # Handle special markers (including various dash patterns and Chinese markers)
    empty_markers = {
        '--', '---', '----', 'nan', 'None', '', 'NaN', 'N/A', 'n/a',
        '除權', '除息', '除權息',  # Ex-rights, ex-dividend markers
        'X', 'x',  # Common placeholder
    }
    if s in empty_markers:
        return ""
    # Also treat all-dash strings as empty
    if s and all(c == '-' for c in s):
        return ""
    return s


def write_error_report(date_str, category, issue):
    """Write a single error to error_processor.md and raise exception to stop"""
    error_file = Path("/app/error_processor.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    report = f"\n## Data Quality Error - {date_str}\n"
    report += f"**Detected at:** {timestamp}\n"
    report += f"**Category:** {category}\n"
    report += f"**Error:** {issue}\n"
    report += "\n**Processing stopped. Fix this error before continuing.**\n"
    report += "---\n"

    with open(error_file, 'a', encoding='utf-8') as f:
        f.write(report)

    print(f"\n❌ Data quality error in {category}:")
    print(f"   {issue}")
    print(f"📝 Report written to error_processor.md")


def get_processed_date_path(category, date_str, market=None):
    """Get path to processed data file, compatible with old/new directory structures"""
    if category in ("quarterly_reports", "income_statement", "balance_sheet", "cash_flow", "monthly_revenue"):
        if market:
            return Path(f"data/processed/{category}/date={date_str}/{market}.csv")
        return Path(f"data/processed/{category}/date={date_str}/all.csv")

    new_dir = Path(f"data/processed/{category}/{date_str[:4]}/{date_str}")
    old_dir = Path(f"data/processed/{category}/date={date_str}")

    base_dir = new_dir if new_dir.exists() else old_dir
    if market:
        return base_dir / f"{market}.csv"
    return base_dir / "all.csv"


class DataQualityCheckerBase(ABC):
    """Base class for category-specific data quality checkers"""

    def __init__(self, date_str):
        self.date_str = date_str
        self.raw_file_cache = {}  # Cache for raw file contents

    @property
    @abstractmethod
    def category(self) -> str:
        """Return the category name (e.g., 'daily_quotes', 'margin_trading')"""
        pass

    @property
    def markets(self) -> list:
        """Return list of markets to check. Override if needed."""
        return ['sii', 'otc']

    @property
    def key_columns(self) -> list:
        """Return list of key columns to check for NULL values. Override per category."""
        return []

    @property
    def null_threshold(self) -> float:
        """Return the threshold for NULL percentage warning. Override per category."""
        return 50.0

    def get_file_path(self, market=None):
        """Get the file path for this category and market"""
        return get_processed_date_path(self.category, self.date_str, market)

    def check(self):
        """Main check method - runs all checks for this category"""
        print(f"Checking {self.category}...")

        for market in self.markets:
            file_path = self.get_file_path(market)

            if not file_path.exists():
                self._handle_missing_file(file_path, market)
                continue

            try:
                df = pd.read_csv(file_path)

                if len(df) == 0:
                    self._raise_error(f"{self.category} {market}: File is empty (0 rows)")

                # Run standard checks
                self._check_key_columns(df, market)

                # Run category-specific checks
                self._check_category_specific(df, market)

                # Run lineage verification (full column-level)
                self._verify_lineage(df, market)

            except DataQualityError:
                raise
            except Exception as e:
                self._raise_error(f"{self.category} {market}: Error reading file - {str(e)}")

    def _handle_missing_file(self, file_path, market):
        """Handle missing file - override if missing file is acceptable"""
        self._raise_error(f"{self.category}: Missing file {file_path}")

    def _check_key_columns(self, df, market):
        """Check key columns for NULL values"""
        for col in self.key_columns:
            if col not in df.columns:
                self._raise_error(f"{self.category} {market}: Missing column '{col}'")

            null_count = df[col].isna().sum()
            null_pct = (null_count / len(df)) * 100

            if null_pct > self.null_threshold:
                self._raise_error(
                    f"{self.category} {market}: Column '{col}' has {null_pct:.1f}% NULL values "
                    f"({null_count}/{len(df)} rows)"
                )

    def _check_category_specific(self, df, market):
        """Override this method to add category-specific checks"""
        pass

    def _verify_lineage(self, df, market):
        """Verify source lineage - full column-level verification"""
        label = f"{self.category} {market}"

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
        """
        Compare processed value with raw value.
        Override this method for category-specific comparison logic.

        Default behavior:
        - If processed is float and raw is int-like, convert to int and compare
        - Otherwise, compare cleaned string values
        """
        # Clean raw value
        raw_clean = clean_value_for_comparison(raw_val)

        # Handle empty values
        if pd.isna(processed_val) or str(processed_val) in ('', 'nan', 'None', 'NaN'):
            # Empty processed should match empty raw
            return raw_clean == "" or raw_clean == "--"

        processed_str = str(processed_val)

        # Try numeric comparison
        try:
            # Check if raw is integer-like (no decimal point)
            if '.' not in raw_clean and raw_clean.lstrip('-').isdigit():
                raw_int = int(raw_clean)
                # Check if processed is a float
                if '.' in processed_str:
                    processed_float = float(processed_str)
                    # Convert float to int for comparison
                    return int(processed_float) == raw_int
                else:
                    return int(processed_str) == raw_int

            # Both are floats
            if raw_clean.replace('.', '').replace('-', '').isdigit():
                raw_float = float(raw_clean)
                processed_float = float(processed_str)
                # Use tolerance for float comparison
                return abs(processed_float - raw_float) < 0.0001
        except (ValueError, TypeError):
            pass

        # String comparison
        processed_clean = clean_value_for_comparison(processed_val)

        # Handle symbol format like ="0050"
        if processed_clean in raw_clean or raw_clean in processed_clean:
            return True

        return processed_clean == raw_clean

    def _resolve_file_path(self, src_file, label, idx):
        """Resolve source file path"""
        full_path = Path(src_file)
        if not full_path.exists():
            if not src_file.startswith("/"):
                cwd = Path.cwd()
                p1 = cwd / src_file
                p2 = cwd.parent / src_file
                if p1.exists():
                    return p1
                elif p2.exists():
                    return p2

            self._raise_error(f"{label} row {idx}: Source file not found: {src_file}")
            return None
        return full_path

    def _read_raw_file(self, full_path, label, idx):
        """Read raw file with caching"""
        cache_key = str(full_path)
        if cache_key not in self.raw_file_cache:
            try:
                with open(full_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                    self.raw_file_cache[cache_key] = f.readlines()
            except Exception as e:
                self._raise_error(f"{label} row {idx}: Error reading source file: {str(e)}")
                return None

        return self.raw_file_cache[cache_key]

    def _raise_error(self, message):
        """Write error and raise exception to stop processing"""
        write_error_report(self.date_str, self.category, message)
        raise DataQualityError(message)
