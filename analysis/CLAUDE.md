# Analytics & EPS Prediction Guide

This directory contains the machine learning pipeline for predicting future EPS using multi-dimensional financial data.

## Core Methodology: Point-in-Time & Staged Prediction

The system implements a **Point-in-Time (PIT)** logic to eliminate Look-ahead Bias in backtesting and daily analysis.

1.  **Financial Publication Baseline**: Predictions and valuations are anchored to official publication deadlines (e.g., Q2 is available on Aug 14).
2.  **Forward TTM (The "Swap" Logic)**:
    - **Official TTM**: Sum of the last 4 published quarters.
    - **Forward TTM**: Sum of the last 3 published quarters + **1 predicted quarter** (dropping the oldest).

## Project Structure

The analytics module is organized by model versions:

- **`v1/` (Proof of Concept)**: Simple baseline test using basic metrics. **[DEPRECATED]**
- **`v2/` (Seasonality)**: Adds historical context and monthly revenue YoY trends.
- **`v3/` (Full Integration)**: Adds quality of earnings (OCF ratio) and financial depth (Retained Earnings).
- **`v4/` (Ratio-Based Elite)**: Integrates 15+ financial ratios. Implements **Expanding Window Backtesting** and decoupled DB persistence. **[Current Production Standard]**

## Model Performance (PIT Evaluation)

| Version | Evaluation Method | Key Features | Status |
|---------|-------------------|--------------|--------|
| **v2/v3**| Single 2024 Holdout | Seasonality & OCF | Legacy |
| **v4**  | **Multi-fold Expanding** | **Full Ratios (ROE, Debt, etc.)** | **Production** |

## How to Run (V4 Standard)

Use the `backend` container. V4 is designed to be parameterized and side-effect free by default.

### 1. Prepare Data
```bash
# Default: 2021 to 2024
docker compose run --rm backend python analysis/v4/prepare_data.py --start-year 2021 --end-year 2024
```

### 2. Train & Experiment (Safe Mode)
By default, this will run an expanding window backtest and print metrics without touching the DB.
```bash
docker compose run --rm backend python analysis/v4/train.py
```

### 3. Production Deployment (Save to DB)
Use the `--save-db` flag to persist predictions into the `eps_predictions` table.
```bash
docker compose run --rm backend python analysis/v4/train.py --save-db --target-year 2024 --target-quarter Q3
```

## Engineering Standards (v4+)

- **Decoupling**: Model evaluation logic is separated from database persistence.
- **CLI first**: Hardcoded values (quarters, symbols) are moved to CLI arguments.
- **Encoding**: All files must use UTF-8 without BOM. Comments are in Traditional Chinese for team maintenance.
- **Robustness**: Multi-year expanding window backtests are mandatory for performance claims.
