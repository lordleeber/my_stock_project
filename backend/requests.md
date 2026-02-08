# Backend API Data Integrity Report

Date: 2026-02-08
Reported by: AI Agent (Strategy & Data Specialist)

## 1. Systematic Data Integrity Issue: Mass Outliers (Daily Quotes)
**Status:** PARTIALLY RESOLVED (Pipeline Hardened, 2020 Fixed)
**Summary:** A full-market scan (2020-2026) revealed over 6,100 records with daily price movements exceeding 11% (violating Taiwan Stock Market's 10% limit).

**Update (2026-02-08):**
- **Root Cause Identified**: Legacy `split(",")` logic in `processor/utils.py` failed on company names with commas or ragged CSV lines from TWSE.
- **Harden Implementation**: 
    - Switched to standard `csv` module for robust parsing.
    - Added dynamic column alignment to handle missing/extra commas.
    - Enhanced `data_quality_checker.py` with internal OHLC logic verification.
    - Modified `scripts/daily_update.sh` to HALT ingestion on DQ failure.
- **Data Backfill**: 
    - **Year 2020**: Fully verified and backfilled (0 remaining issues).
    - **Cluster B & C (2025)**: Major anomalies fixed.
    - **Note**: Some dates still show jumps due to legitimate dividends/splits. Reference data for corporate actions (2020-2025) has been collected in `data/raw/` for future automated validation.

**Impact:**
- Backtesting performance metrics (Max Drawdown/Upside) are unusable without these fixes.
- Technical indicators (MA, RSI, Bollinger) are severely distorted on corrupted dates.

**Remaining Task:**
- Integrate `data/raw/ex_dividend` and `capital_reduction` reference tables into the `data_quality_checker.py` to automatically whitelist legitimate price jumps.

---

## 2. Missing Historical Monthly Revenue (KUDOS)
**Status:** RESOLVED
**Note:** The backfill of 2020-2024 revenue data is successful and has enabled our historical screening tools.
