# Backend API Issues & Requests (Fundamental Analysis Focus)

Date: 2026-02-07
Reported by: AI Agent (Fundamental Analysis Specialist)

## 1. Detailed Financial Statement APIs are Empty
**Status:** RESOLVED
**Details:**
- **Fix:** Performed a bulk import of 23 quarters (2020Q1 to 2025Q3) for `income_statement`, `balance_sheet`, and `cash_flow`.
- **Validation:** Verified `GET /raw/income-statements?symbol=2330&start_date=2020Q1&end_date=2025Q2` returns correct data.
- **Root Cause:** Initial import only targeted 2025Q3; historical data was present in `processed/` but not loaded into DB.

## 2. Missing raw totals in quarterly_reports (RESOLVED)
**Status:** RESOLVED
**Details:** 
- The redesigned `quarterly_reports` table focuses on YoY metrics and ratios. 
- **Solution:** Raw totals like `total_assets`, `total_liabilities`, `current_assets`, etc., are now fully available via the new detailed APIs:
  - `GET /raw/balance-sheets`
  - `GET /raw/income-statements`
- This fulfills the requirement of providing access to raw financial totals across all historical quarters.
