# Backend Guide (for AI Assistants)

FastAPI backend serving the stock analysis frontend. Integrates `scanner/` and `strategy/` modules.

## Tech Stack

- **FastAPI** 0.110.0 + **Pydantic** 2.6.3
- **SQLAlchemy** 2.0.29 (raw SQL via `text()`, no ORM models)
- **PostgreSQL** 15 via psycopg2
- **Uvicorn** with `--reload` (auto-reload on file changes)

## Project Structure

```
backend/
├── main.py              # All endpoints, models, and app config
├── create_indexes.py    # DB index creation utility
├── Dockerfile
└── requirements.txt

scanner/                 # Imported by backend at runtime
├── volume_spike_scanner.py   # SQL-based volume spike detection
└── plot_candlestick.py       # CLI charting (not used by API)

strategy/                # Imported by backend at runtime
├── core.py              # Backtest engine (StrategyConfig, run_backtest)
└── __init__.py
```

## Running

```bash
# Via Docker (recommended)
docker compose up -d backend

# Rebuild after changing Dockerfile or requirements.txt
docker compose up -d --build backend

# After changing only Python code (volume-mounted):
# NOTE: uvicorn --reload watches /app/main.py, but the Dockerfile
# COPYs main.py to /app/main.py. Volume mounts go to /app/backend/.
# So code changes require a rebuild OR manual restart:
docker compose stop backend && docker compose up -d backend
```

## IMPORTANT: File Path Gotcha

The Dockerfile copies `backend/main.py` → `/app/main.py`. The volume mount `./backend:/app/backend` maps to `/app/backend/main.py`. Uvicorn imports from `/app/main.py` (the baked-in copy).

**This means:** Editing `backend/main.py` on the host does NOT auto-reload the running server. You must either:
1. `docker compose up -d --build backend` (rebuild image)
2. `docker compose stop backend && docker compose up -d backend` (restart)

The `scanner/` and `strategy/` volume mounts work the same way — they're COPYed at build time.

## Database Connection

```python
def get_db_url():
    # Env vars: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
    # Defaults: user, password, db, 5432, stock_db
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
```

All queries use raw SQL via `sqlalchemy.text()`. No ORM models — just `engine.connect()` + `conn.execute(sql, params)`.

## API Endpoints

### Scanner

| Endpoint | Method | Key Params | Response Model |
|----------|--------|-----------|----------------|
| `/scanner/volume-spike` | GET | `date` (YYYY-MM-DD), `min_volume` (5000000), `volume_ratio` (4.0), `avg_days` (10), `filter_long_shadow` (true) | `List[VolumeSpikeResult]` |
| `/scanner/candlestick/{symbol}` | GET | `date`, `days_before` (30), `days_after` (10) | `List[CandlestickData]` |
| `/scanner/institutional/{symbol}` | GET | `date`, `days_before` (90), `days_after` (90) | `List[InstitutionalData]` |

### Backtest

| Endpoint | Method | Body | Response Model |
|----------|--------|------|----------------|
| `/backtest/run` | POST | `BacktestRequest` JSON | `BacktestResult` |

### Market Data

| Endpoint | Method | Key Params | Response Model |
|----------|--------|-----------|----------------|
| `/quotes/top-volume` | GET | `date`, `limit` (10), `sort` (asc/desc) | `List[StockQuote]` |
| `/analysis/ma` | GET | `date`, `limit`, `sort` | `List[MAQuote]` |
| `/analysis/vma` | GET | `date`, `limit`, `sort` | `List[VMAQuote]` |

### Health

| Endpoint | Method | Response |
|----------|--------|---------|
| `/health` | GET | `{"status": "ok", "db_connection": "success"}` |

## Pydantic Models (all in main.py)

### VolumeSpikeResult
```
symbol, name, date, open, high, low, close, volume, volume_ratio,
distance_from_high_pct?, upper_shadow_ratio?,
ma5?, ma10?, ma20?, ma60?, k?, d?, rsi6?, rsi12?, macd_dif?, macd_dea?
```

### CandlestickData
```
date, open, high, low, close, volume, ma5?, ma10?, ma20?, ma60?
```

### InstitutionalData
```
date, foreign_net, trust_net, foreign_held_shares?, trust_held_shares?
```
- `trust_held_shares` is a running sum of `trust_net` from earliest data (approx. value starting from 0 at 2022-01-03)
- Computed via CTE with `SUM(trust_net) OVER (ORDER BY date)` across ALL dates, then filtered to display range

### BacktestRequest
```
start_date, end_date, strategy_mode ("shares"|"amount"), capital (100000),
hold_days (3), allow_pyramiding (true), only_red_candle (false),
take_profit_pct (0.0), stop_loss_pct (0.0)
```

### BacktestResult
```
summary: { total_trades, total_profit, total_cost, roi, win_rate, avg_return }
trades: [{ symbol, name, buy_date, sell_date, buy_price, sell_price, shares, profit, return_rate }]
```

## Database Tables Used

| Table | Key Columns | Used By |
|-------|------------|---------|
| `daily_quotes` | date, symbol, open, high, low, close, volume, name, market | Most endpoints |
| `technical_indicators` | date, symbol, ma5-ma240, vma5-vma240, k, d, rsi6, rsi12, macd_dif, macd_dea | Scanner, analysis |
| `institutional_investors` | date, symbol, foreign_net, trust_net | Institutional API |
| `foreign_holding` | date, symbol, foreign_held_shares | Institutional API |

Indexes: `idx_daily_quotes_date_symbol`, `idx_daily_quotes_symbol_date`

## Scanner Filter Logic (volume-spike)

The scanner SQL in `scanner/volume_spike_scanner.py` applies these filters:
1. `volume >= min_volume` (default 5M shares)
2. `volume >= avg_volume_Nd * volume_ratio` (default 4x vs 10-day avg)
3. `close > open` (red candle / bullish close)
4. `close >= MA60` (above 60-day moving average; stocks without MA60 are excluded)
5. `close >= 90-day highest close` (near-term high)
6. Optional: upper shadow ratio < 1.0 (filter long upper shadows)

## Strategy / Backtest Logic

Located in `strategy/core.py`:
- **Signal**: `volume > vma10 * 5`
- **Entry**: Buy at next trading day's open
- **Exit**: Time-based (N days), take-profit, or stop-loss
- **Costs**: Commission 0.1425% + Tax 0.3% (Taiwan market standard)
- **Modes**: Fixed shares (1000/trade) or fixed capital amount

## CORS Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Error Handling Pattern

All endpoints follow this pattern:
```python
try:
    # SQL query + data processing
    return data
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()
    raise HTTPException(status_code=500, detail=str(e))
```

## Testing Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Volume spike scanner
curl "http://localhost:8000/scanner/volume-spike?date=2025-10-03"

# Candlestick chart data
curl "http://localhost:8000/scanner/candlestick/6548?date=2025-10-03"

# Institutional data
curl "http://localhost:8000/scanner/institutional/2330?date=2025-12-01"

# Backtest
curl -X POST http://localhost:8000/backtest/run \
  -H "Content-Type: application/json" \
  -d '{"start_date":"2025-01-01","end_date":"2025-06-30","hold_days":3}'

# Top volume
curl "http://localhost:8000/quotes/top-volume?date=2025-10-03&limit=5"
```

## Adding a New Endpoint

1. Define Pydantic response model in `main.py`
2. Add endpoint function with `@app.get()` or `@app.post()`
3. Write raw SQL via `text()`, execute with `engine.connect()`
4. Map rows to Pydantic models
5. Rebuild: `docker compose up -d --build backend`
