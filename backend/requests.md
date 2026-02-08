# Backend API Issues & Requests (Fundamental Analysis Focus)

Date: 2026-02-08
Reported by: AI Agent (Fundamental Analysis Specialist)

## 1. Missing Historical Monthly Revenue Data
**Status:** RESOLVED
**Details:**
- **Fix:** Performed a bulk process and import of 60 months (2020M01 to 2024M12) using the new `YYYYMXX` format.
- **Validation:** Verified `GET /raw/monthly-revenue?symbol=2330&start_date=2024M01` returns correct data.
- **Impact:** Fundamental screeners can now calculate multi-month growth trends for historical dates back to 2020.

## 2. API Format Consistency (KUDOS)
**Observation:** The update to `YYYYMXX` format for revenue and `YYYYQX` for quarterly reports is excellent and has been successfully integrated into the screener logic.

## 3. Stock Info API (KUDOS)
**Observation:** The addition of the `/raw/stock-info` endpoint with `industry` data has enabled our new "Industry-Adjusted PE" scoring system, significantly improving ranking accuracy for different sectors (e.g., AI vs. Construction).