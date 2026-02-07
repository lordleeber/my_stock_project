# Backend API Issues & Requests

Date: 2026-02-07
Reported by: AI Agent (Fundamental Analysis Specialist)

## 1. /raw/daily-quotes 500 Internal Server Error (FIXED)
**Status:** Fixed in commit `ff4d090`.
**Solution:** Added recursive value cleaning in `get_raw_data` to convert non-JSON compliant float values (NaN, Infinity) to `null`.

## 2. Character Encoding (Mojibake) in Stock Names (NOT REPRODUCED)
**Status:** Investigated.
**Findings:** 
- Direct database inspection via `psql` shows names are correctly stored in UTF-8 (e.g., "台泥", "晶心科").
- Attempted to search for the reported Mojibake string in the database with 0 results.
- **Recommendation:** This is likely a Client-side display issue. Please ensure your API client (Browser, Terminal, or VS Code Preview) is configured to decode JSON as UTF-8.

## 3. API Enhancement Requests
- **Pagination Support (IMPLEMENTED):** Added `offset` parameter to all `/raw/*` endpoints in commit `ff4d090`.
- **Improved Error Logging (PLANNED):** Consider adding structured logging for better debugging of validation errors.
