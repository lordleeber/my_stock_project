# Analytics & EPS Prediction Guide

This directory contains the machine learning pipeline for predicting future EPS using multi-dimensional financial data.

## Core Methodology: Point-in-Time & Staged Prediction

The system implements a **Point-in-Time (PIT)** logic to eliminate Look-ahead Bias in backtesting and daily analysis.

1.  **Financial Publication Baseline**: Predictions and valuations are anchored to official publication deadlines (e.g., Q2 is available on Aug 14).
2.  **Forward TTM (The "Swap" Logic)**:
    - **Official TTM**: Sum of the last 4 published quarters.
    - **Forward TTM**: Sum of the last 3 published quarters + **1 predicted quarter** (dropping the oldest).
    - This creates a **leading indicator** that updates as soon as monthly revenue is available, well before the official earnings call.

## Data Workflow & Persistence

The analysis results are no longer just CSVs; they are persisted into the database to fuel the valuation engine.

- **`db_utils.py`**: A shared utility module that standardizes saving model outputs to the `eps_predictions` table.
- **`valuation_daily`**: The final destination. Updated daily via `calculator/calculate_valuation.py`, integrating:
    - Daily Price (`close`)
    - Forward EPS (`ttm_eps_forward`)
    - Target Price (`predict_target_price` = `ttm_eps_forward * pe_official`)
    - Forward Percentile (`pe_percentile_forward`)

## Project Structure

- **`v1/` - `v4/`**: Progressive iterations of the EPS prediction models.
- **`db_utils.py`**: Shared database operations for model output.
- **`CLAUDE.md`**: This guide.

## How to Run

### 1. Model Training & Prediction (Persistence)
Use the `backend` container. V4 is the current standard.
```bash
# Prepare full history features
docker compose run --rm backend python analysis/v4/prepare_data.py
# Train and save predictions to 'eps_predictions' table
docker compose run --rm backend python analysis/v4/train.py
```

### 2. Daily Analytics (Calculations)
The analysis results are automatically utilized by the **`daily_calculator.sh`** task.
```bash
# Runs technical indicators followed by PIT forward-looking valuations
./schedules/daily_calculator.sh 20260211
```

## Model Performance (2024Q3 PIT Evaluation)

| Version | Features | 2330 Pred (Real: 12.55) | Status |
|---------|----------|-------------------------|--------|
| **v2**  | Seasonality | 10.82 | Good |
| **v3**  | OCF + Retained Earnings | 11.93 | **Strong** |
| **v4**  | **Full Financial Ratios (ROE)** | **12.17** | **Elite** |

## Database Dependencies

- **`eps_predictions`**: Input for `valuation_daily`.
- **`valuation_daily`**: Primary table for screening and PE bands.
- **`quarterly_reports`**: Requires dual-column schema (`_q` and `_acc`) for TTM calculations.
