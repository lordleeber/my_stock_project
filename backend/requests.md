# Backend Feature Requests & Tasks

This document tracks new feature requests and technical tasks for the backend.

## Pending Requests

(No pending requests)

---

## Recently Completed

- **ML Training Data Endpoint**: Added `GET /ml/training-data` for bulk historical data retrieval. (2026-02-06)
- **Database Index Optimization**: Created composite indexes for `technical_indicators`, `institutional_investors`, and `foreign_holding`. (2026-02-06)

---

## Data Recovery Log

### 2026-02-07: Database Indexes Recovery

**Issue:**
Commit a076a50 performed database cleanup that resulted in loss of critical composite indexes:
- `idx_daily_quotes_date_symbol`
- `idx_daily_quotes_symbol_date`
- `idx_institutional_investors_symbol_date`
- `idx_foreign_holding_symbol_date`

**Impact:**
ML training data endpoint query performance degraded from ~50ms to several seconds due to full table scans.

**Recovery:**
All 5 indexes recreated using `backend/create_indexes.py`. Performance restored.

**Status:** ✅ Resolved
