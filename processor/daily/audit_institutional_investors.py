#!/usr/bin/env python3
"""
Data Quality Checker for institutional_investors category
"""

from audit_base import DataQualityCheckerBase, clean_value_for_comparison
import pandas as pd


class InstitutionalInvestorsChecker(DataQualityCheckerBase):
    """Checker for institutional_investors - buy/sell/net data"""

    @property
    def category(self):
        return "institutional_investors"

    @property
    def key_columns(self):
        return ["foreign_net", "trust_net", "dealer_net"]

    @property
    def null_threshold(self):
        return 50.0

    # All numeric columns (integers in raw, floats in processed)
    INTEGER_COLUMNS = {
        "foreign_buy",
        "foreign_sell",
        "foreign_net",
        "foreign_dealer_buy",
        "foreign_dealer_sell",
        "foreign_dealer_net",
        "trust_buy",
        "trust_sell",
        "trust_net",
        "dealer_self_buy",
        "dealer_self_sell",
        "dealer_self_net",
        "dealer_hedge_buy",
        "dealer_hedge_sell",
        "dealer_hedge_net",
        "dealer_net",
        "total_net",
        "foreign_total_buy",
        "foreign_total_sell",
        "foreign_total_net",
        "dealer_total_buy",
        "dealer_total_sell",
    }

    STRING_COLUMNS = {"symbol", "name"}

    def _compare_values(self, processed_val, raw_val, col_name):
        """Custom comparison for institutional_investors"""
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

    def _verify_lineage(self, df, market):
        """Override to handle ETFs/special securities with fewer columns

        Some securities (e.g., ETFs like 00851) have only 17 columns instead of 20.
        They are missing the detailed dealer breakdown (dealer_self_*, dealer_hedge_*).
        The processor pads these rows with empty values, but the src_col mapping
        points to columns that don't exist in the raw file.
        """
        from audit_base import parse_csv_line, DEBUG

        # 🔧 Local debug switch - set to True to see detailed column verification
        DEBUG_COLUMN_VERIFICATION = False

        label = f"{self.category} {market}"

        # Check lineage columns exist
        for col in ["src_file", "src_row", "src_col"]:
            if col not in df.columns:
                self._raise_error(f"{label}: Missing lineage column '{col}'")
            if df[col].isna().any():
                self._raise_error(
                    f"{label}: Found NULL values in lineage column '{col}'"
                )

        # Get schema columns (exclude lineage columns)
        schema_cols = [
            c for c in df.columns if c not in ("src_file", "src_row", "src_col")
        ]

        # Columns that may be missing in ETFs/special securities
        # ETFs typically have 17 fields instead of 20, missing:
        # - Field 18: dealer_hedge_net (自營商買賣超股數(避險))
        # - Field 19: total_net (三大法人買賣超股數)
        # - Field 20: empty
        OPTIONAL_DEALER_COLUMNS = {
            "dealer_hedge_net",  # Field 18
            "total_net",  # Field 19
        }

        # Verify each row
        for idx, row in df.iterrows():
            src_file = str(row["src_file"])
            src_col = str(row["src_col"])

            try:
                src_row = int(float(row["src_row"]))
            except (ValueError, TypeError):
                self._raise_error(
                    f"{label} row {idx}: Invalid src_row value '{row['src_row']}'"
                )

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
            raw_field_count = len(raw_fields)

            # Detect if this is a special security (ETF) with fewer columns
            is_special_security = raw_field_count < 20

            if DEBUG and is_special_security and idx % 50 == 0:
                print(
                    f"    Row {idx} ({row.get('symbol', 'N/A')}): Special security with {raw_field_count} fields"
                )

            # Parse src_col indices
            col_indices = src_col.split("#")

            if len(col_indices) != len(schema_cols):
                self._raise_error(
                    f"{label} row {idx}: src_col length ({len(col_indices)}) != "
                    f"schema_cols length ({len(schema_cols)})"
                )

            # Verify ALL columns
            # Print every 100 rows, or specific interesting rows (e.g., ETF at row 102)
            should_debug_print = DEBUG_COLUMN_VERIFICATION and (
                idx % 100 == 0 or idx == 102
            )
            if should_debug_print:
                print(
                    f"\n🔍 Detailed verification for row {idx} (symbol: {row.get('symbol', 'N/A')}):"
                )
                print(f"   src_file: {src_file}")
                print(f"   src_row: {src_row}")
                print(f"   src_col: {src_col}")
                print(f"   raw_field_count: {raw_field_count}")
                print(f"   is_special_security: {is_special_security}")

            for col_idx, (col_name, src_idx_str) in enumerate(
                zip(schema_cols, col_indices)
            ):
                # Skip processing-added columns (x)
                if src_idx_str == "x":
                    if should_debug_print:
                        print(
                            f"   [{col_idx:2d}] {col_name:25s} <- 'x' (processing-added, skipped)"
                        )
                    continue

                try:
                    src_idx = int(src_idx_str) - 1  # Convert to 0-based
                except ValueError:
                    self._raise_error(
                        f"{label} row {idx} col '{col_name}': Invalid src_col index '{src_idx_str}'"
                    )

                # Special handling for optional dealer columns in special securities
                if is_special_security and src_idx >= raw_field_count:
                    if col_name in OPTIONAL_DEALER_COLUMNS:
                        # Verify that the processed value is 0 or NULL (padded column)
                        processed_val = row.get(col_name, None)
                        if should_debug_print:
                            print(
                                f"   [{col_idx:2d}] {col_name:25s} <- [{src_idx + 1:2d}] OUT OF RANGE (optional, padded) processed={processed_val}"
                            )
                        if pd.notna(processed_val) and float(processed_val) != 0.0:
                            self._raise_error(
                                f"{label} row {idx} col '{col_name}': Special security with {raw_field_count} fields "
                                f"should have 0 or NULL for padded column, but got '{processed_val}'"
                            )
                        # Skip raw verification for this padded column
                        continue
                    else:
                        self._raise_error(
                            f"{label} row {idx} col '{col_name}': src_col index {src_idx + 1} "
                            f"out of range (raw has {raw_field_count} fields), and this is not an optional dealer column"
                        )

                if src_idx >= len(raw_fields):
                    self._raise_error(
                        f"{label} row {idx} col '{col_name}': src_col index {src_idx + 1} "
                        f"out of range (raw has {len(raw_fields)} fields)"
                    )

                # Get values for comparison
                processed_val = row.get(col_name, "")
                raw_val = raw_fields[src_idx]

                if should_debug_print:
                    match_result = (
                        "✓"
                        if self._compare_values(processed_val, raw_val, col_name)
                        else "✗"
                    )
                    print(
                        f"   [{col_idx:2d}] {col_name:25s} <- [{src_idx + 1:2d}] {match_result} processed='{processed_val}' raw='{raw_val}'"
                    )

                # Compare values using category-specific logic
                if not self._compare_values(processed_val, raw_val, col_name):
                    self._raise_error(
                        f"{label} row {idx} col '{col_name}': Value mismatch! "
                        f"Processed='{processed_val}', Raw[{src_idx + 1}]='{raw_val}'"
                    )

            if DEBUG and idx % 100 == 0:
                print(f"    Verified {idx + 1}/{len(df)} rows...")
