### Deep Learning Team Requirements

To facilitate Reinforcement Learning (RL) training with high efficiency, we need the following API updates and database optimizations.

#### 1. New Endpoint: `GET /ml/training-data`
This endpoint should provide bulk historical data for multiple stocks to minimize API round-trips.

**Parameters:**
- `symbols` (optional): Comma-separated list of symbols (e.g., "2330,2317,2454"). If omitted, provide data for all active stocks.
- `start_date`: YYYY-MM-DD
- `end_date`: YYYY-MM-DD
- `include_indicators`: boolean (default: true) - Join with `technical_indicators` table.
- `include_institutional`: boolean (default: true) - Join with `institutional_investors` and `foreign_holding` tables.

**Response Body (JSON):**
A list of records, sorted by `date` and `symbol`:
```json
[
  {
    "date": "2024-01-02",
    "symbol": "2330",
    "open": 590.0,
    "high": 593.0,
    "low": 588.0,
    "close": 593.0,
    "volume": 25000000,
    "ma5": 588.2,
    "ma10": 585.5,
    "k": 75.2,
    "d": 70.1,
    "rsi6": 65.5,
    "foreign_net": 1500,
    "trust_net": 200,
    "foreign_held_shares": 18000000000
  },
  ...
]
```

#### 2. Database Optimization
- Ensure `daily_quotes` has a composite index on `(symbol, date)`.
- Ensure `technical_indicators` has a composite index on `(symbol, date)`.
- Ensure `institutional_investors` has a composite index on `(symbol, date)`.

#### 3. (Optional) Binary Stream Support
If the JSON response size exceeds 50MB per request, please consider supporting a `format=parquet` or `format=csv` stream to reduce parsing overhead on the client side.
