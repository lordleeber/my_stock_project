# Backend API Issues & Requests (Fundamental Analysis Focus)

Date: 2026-02-07

## 1. /raw/quarterly-reports Data Loss (FIXED)
**Status:** FIXED on 2026-02-07
**Fixes:**
- Corrected OTC fuzzy matching logic to prioritize "每股稅後純益" (EPS) before "稅後純益" (Net Income) to avoid substring collision.
- Fixed SII index mappings for `current_ratio` (Col 17) and `quick_ratio` (Col 18).
- Improved OTC `name` extraction fallback.
- Implemented multi-row header merging in the processor for more robust fuzzy matching.
- **Note:** `operating_cash_flow` is actually NOT present in the standard TWSE/TPEx "Financial Information Summary" (C05001/O_XLS) files. The processor has been updated to remove incorrect mapping of this field from summary files.

## 2. Missing Balance Sheet Raw Totals (PENDING NEW DATA SOURCE)
**Status:** BLOCKED - Data not in current raw files.
**Details:**
- The current scraper fetches "Summary Tables" (彙總報表) which only contain key ratios, not the full Balance Sheet or Cash Flow Statement.
- **Required Action:** Need to implement a new scraper for MOPS "Balance Sheet Summary" and "Cash Flow Summary" to populate `total_assets`, `total_liabilities`, `current_assets`, `current_liabilities`, and `operating_cash_flow`.
- **Planned Source:** MOPS `t51sb07` (Balance Sheet) and `t51sb09` (Cash Flow).