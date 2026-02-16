# Analytics & EPS Prediction Guide

This directory contains the machine learning pipeline for predicting future EPS using multi-dimensional financial data.

## Project Structure

The analytics module is organized by model versions, representing the evolution of our methodology:

- **`v1/` (Baseline)**: Focuses on basic fundamental metrics (Q2 EPS, margins) and Q3 revenue total.
- **`v2/` (Seasonality)**: Adds historical context by including last year's performance and monthly revenue YoY trends.
- **`v3/` (Full Integration)**: The most advanced version. Adds quality of earnings (OCF ratio) and financial depth (Retained Earnings). **[Recommended]**

## How to Run

Use the `backend` container for execution as it contains `scikit-learn` and `joblib`. Each version has its own `prepare_data.py` and `train.py`.

### Example (Running V3):
```bash
# 1. Prepare data (extracts history from 2021 to 2024)
docker compose run --rm -v $(pwd):/app -w /app backend python analysis/v3/prepare_data.py

# 2. Train and Evaluate
docker compose run --rm -v $(pwd):/app -w /app backend python analysis/v3/train.py
```

## Model Comparison (2024Q3 Evaluation)

| Version | Key Features Added | Result (MAE) | Focus |
|---------|-------------------|--------------|-------|
| **v1**  | Q2 EPS, Q2 Margins, Q3 Total Rev | 0.4778 | Base fundamental + revenue sum |
| **v2**  | **Seasonality**: LY Q3 EPS, Monthly Revenue **YoY** | 0.5208 | Capturing seasonal trends & momentum |
| **v3**  | **Financial Health**: OCF Ratio, Retained Earnings Ratio | **0.5255** | Multi-table integration (Quality of earnings) |

*Note: MAE values for v2/v3 reflect a more rigorous out-of-time testing (2020-2023 train, 2024 test).*

## Key Features & Importances (v3 Model)

1. **`q2_eps` (~70%)**: The strongest anchor for future performance.
2. **`q2_re_ratio` (~10%)**: (Retained Earnings / Capital). Indicates financial depth.
3. **`ly_q3_eps` (~8%)**: Captures industry-specific seasonality.
4. **`rev_trend` & `rev_yoy`**: Monthly momentum and YoY expansion.
5. **`q2_ocf_ratio`**: (Operating Cash Flow / Net Income). Validates earnings quality.

## Database Dependencies

The models rely on the **Dual-Column Schema** (`_q` and `_acc`) implemented in `quarterly_reports`, `income_statement`, and `cash_flow`. Ensure the data pipeline has been run sequentially to calculate these values before training.
