# Analytics & EPS Prediction Guide

This directory contains the machine learning pipeline for predicting future EPS using multi-dimensional financial data (Income Statement, Balance Sheet, Cash Flow, and Monthly Revenue).

## Overview

The core objective is to predict the **next quarter's single EPS (`target_eps`)** before it is officially announced, using information available shortly after the quarter ends (e.g., predicting Q3 EPS in early October once September revenue is public).

### Model Evolution (V1 -> V3)

| Version | Key Features Added | Result (MAE) | Focus |
|---------|-------------------|--------------|-------|
| **V1**  | Q2 EPS, Q2 Margins, Q3 Total Rev | 0.4778 | Base fundamental + revenue sum |
| **V2**  | **Seasonality**: LY Q3 EPS, Monthly Revenue **YoY** | 0.5208* | Capturing seasonal trends & momentum |
| **V3**  | **Financial Health**: OCF Ratio, Retained Earnings Ratio | **0.5255** | Multi-table integration (Quality of earnings) |

*\*Note: V2/V3 MAE reflects a more rigorous staged testing compared to V1.*

## Core Methodology: Staged Prediction

We simulate information availability at different time points:
1. **T1 (Aug 14)**: Known Q2 Reports + **July Revenue**.
2. **T2 (Sep 10)**: Known Q2 Reports + July/August Revenue.
3. **T3 (Oct 10)**: Known Q2 Reports + **Full Q3 Revenue** (7, 8, 9M).

## Key Features & Importances (V3 Model)

1. **`q2_eps` (~70%)**: The strongest anchor for future performance.
2. **`q2_re_ratio` (~10%)**: (Retained Earnings / Capital). Indicates financial depth and ability to sustain growth.
3. **`ly_q3_eps` (~8%)**: Captures industry-specific seasonality.
4. **`rev_trend` & `rev_yoy`**: Monthly momentum and year-over-year expansion.
5. **`q2_ocf_ratio`**: (Operating Cash Flow / Net Income). Validates earnings quality.

## File Descriptions

- `prepare_eps_prediction_data.py`: Multi-table JOIN engine. Extracts features from `income_statement`, `balance_sheet`, `cash_flow`, and `monthly_revenue`.
- `train_eps_predictor_v3.py`: Main training script using `RandomForestRegressor`.
- `eps_v3_dataset.csv`: The processed training/testing dataset.
- `eps_predictor_model.pkl`: The trained model binary.

## How to Run

Use the `backend` container as it contains `scikit-learn` and `joblib`.

```bash
# 1. Prepare data (extracts history from 2021 to 2024)
docker compose run --rm -v $(pwd):/app -w /app backend python analysis/prepare_eps_prediction_data.py

# 2. Train and Evaluate
docker compose run --rm -v $(pwd):/app -w /app backend python analysis/train_eps_predictor_v3.py
```

## Future Work

- **Incorporate Inventory**: Currently missing from the summary CSVs. Adding Inventory Turnover would likely improve T3 accuracy.
- **2025Q4 Prediction**: The current model is validated on 2024Q3. Next step is to apply the model to the latest data to predict upcoming 2025Q4 results.
- **Sector-Specific Models**: Training separate models for IC Design vs. Traditional Manufacturing to better capture different margin structures.

## Database Dependencies

The models rely on the **Dual-Column Schema** (`_q` and `_acc`) implemented in `quarterly_reports`, `income_statement`, and `cash_flow`. Ensure the data pipeline has been run sequentially to calculate these values before training.
