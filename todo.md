# TODO List

## Task: Integrate QC Checker into Standalone Converter Scripts

### Root Cause
Currently, only `convert_daily.py` (unified ETL entry point) has integrated quality checking - it automatically runs `data_quality_checker.main()` after processing each date. However, standalone converter scripts (`convert_monthly_revenue.py`, `convert_quarterly_reports.py`, `convert_quarterly_statements.py`, `convert_shareholding_div.py`) process data independently but do NOT automatically validate the output.

This creates an inconsistency:
- **convert_daily.py**: Process → Auto QC → Fail-fast on errors ✅
- **convert_shareholding.py**: Process → Auto QC (ShareholdingChecker only) → Fail-fast on errors ✅ (FIXED)
- **convert_monthly_revenue.py**: Process → Manual QC required ❌
- **convert_quarterly_reports.py**: Process → Manual QC required ❌
- **convert_quarterly_statements.py**: Process → Manual QC required ❌
- **convert_shareholding_div.py**: Process → Manual QC required ❌

The user correctly pointed out that data validation should be integrated into the conversion process, not run as a separate manual step.

### Task Goal
Integrate automatic quality checking into all standalone converter scripts following the same pattern as `convert_shareholding.py`:

1. **convert_monthly_revenue.py**:
   - Import `MonthlyRevenueChecker` from `data_quality_checker_monthly_revenue`
   - After processing each date, run `checker = MonthlyRevenueChecker(date_str); checker.check()`
   - Fail-fast on `DataQualityError` with `sys.exit(1)`

2. **convert_quarterly_reports.py**:
   - No dedicated QC checker exists yet
   - Either: (a) Create a checker, or (b) Skip QC integration if not needed

3. **convert_quarterly_statements.py**:
   - Processes 3 categories: `income_statement`, `balance_sheet`, `cash_flow`
   - No dedicated QC checkers exist yet
   - Either: (a) Create checkers for each category, or (b) Skip QC integration if not needed

4. **convert_shareholding_div.py**:
   - This is legacy (2023/09~2026/02), may not need QC integration
   - Evaluate if it's still actively used

### Implementation Pattern (Reference: convert_shareholding.py)

```python
# At top of file
from data_quality_checker_<category> import <CategoryChecker>
from data_quality_checker_base import DataQualityError

# In main() after process_file() succeeds:
if process_file(file_path, date_str):
    processed_count += 1

    # Run QC immediately
    print(f"Auditing <category> data for {date_str}...")
    try:
        checker = <CategoryChecker>(date_str)
        checker.check()
        print(f"✅ <Category> data quality check passed for {date_str}")
    except DataQualityError as e:
        error_msg = f"<Category> data quality check failed: {str(e)}"
        print(f"❌ {error_msg}")
        print(f"❌ Processing stopped due to data quality error. Fix the issue and re-run.")
        sys.exit(1)
```

### Verification Steps
After integration, test each script:
1. Build processor: `docker compose build processor`
2. Run with FORCE_REPROCESS to see full output
3. Verify QC runs automatically after processing
4. Verify it fails fast on data quality errors

### Files to Modify
- `processor/convert_monthly_revenue.py`
- `processor/convert_quarterly_reports.py` (evaluate first)
- `processor/convert_quarterly_statements.py` (evaluate first)
- `processor/convert_shareholding_div.py` (evaluate if needed)

### Status
- ✅ DONE: `convert_shareholding.py` (integrated ShareholdingChecker)
- ⏳ TODO: Other standalone converters
