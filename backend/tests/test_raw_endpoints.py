import re
import sys
from pathlib import Path
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Add parent directory to path to import main.py
sys.path.insert(0, str(Path(__file__).parent.parent))
from main import app

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _sample_row(engine, table: str, columns: List[str]) -> Dict | None:
    sql = text(f"SELECT {', '.join(columns)} FROM {table} ORDER BY date DESC LIMIT 1")
    with engine.connect() as conn:
        row = conn.execute(sql).mappings().first()
    return dict(row) if row else None


CASES = [
    {
        "endpoint": "/raw/daily-quotes",
        "table": "daily_quotes",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date", "symbol", "name", "market", "open", "high", "low", "close",
            "volume", "value", "transactions", "change", "direction", "bid", "ask", "pe_ratio"
        ],
    },
    {
        "endpoint": "/raw/margin-trading",
        "table": "margin_trading",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date", "symbol", "market", "name",
            "margin_long_buy", "margin_long_sell", "margin_long_cash_repay",
            "margin_long_prev_balance", "margin_long_balance", "margin_long_limit",
            "margin_short_buy", "margin_short_sell", "margin_short_cash_repay",
            "margin_short_prev_balance", "margin_short_balance", "margin_short_limit",
            "offset_balance"
        ],
    },
    {
        "endpoint": "/raw/margin-summary",
        "table": "margin_summary",
        "columns": ["date", "market"],
        "params": ["market"],
        "required_non_empty": ["date", "market"],
        "expected_fields": [
            "date", "market", "item", "buy", "sell", "cash_repay", "prev_balance", "today_balance"
        ],
    },
    {
        "endpoint": "/raw/institutional-investors",
        "table": "institutional_investors",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date", "symbol", "market", "name",
            "foreign_buy", "foreign_sell", "foreign_net",
            "trust_buy", "trust_sell", "trust_net",
            "dealer_buy", "dealer_sell", "dealer_net"
        ],
    },
    {
        "endpoint": "/raw/institutional-summary",
        "table": "institutional_summary",
        "columns": ["date", "market"],
        "params": ["market"],
        "required_non_empty": ["date", "market"],
        "expected_fields": ["date", "market", "institution", "buy", "sell", "net"],
    },
    {
        "endpoint": "/raw/foreign-holding",
        "table": "foreign_holding",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date", "symbol", "market",
            "issued_shares", "foreign_investable_shares", "foreign_held_shares",
            "foreign_investable_ratio", "foreign_held_ratio", "foreign_legal_limit_ratio"
        ],
    },
    {
        "endpoint": "/raw/pe-ratio",
        "table": "pe_ratio",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": ["date", "symbol", "market", "pe_ratio", "dividend_yield", "pb_ratio"],
    },
    {
        "endpoint": "/raw/market-indices",
        "table": "market_indices",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": ["date", "symbol", "name", "market", "close", "change", "change_pct"],
    },
    {
        "endpoint": "/raw/monthly-revenue",
        "table": "monthly_revenue",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date", "symbol", "market",
            "revenue_current", "revenue_last_month", "revenue_last_year",
            "mom_pct", "yoy_pct",
            "revenue_cumulative", "revenue_cumulative_last_year", "cumulative_yoy_pct"
        ],
    },
    {
        "endpoint": "/raw/shareholding",
        "table": "shareholding_div",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
        "required_non_empty": ["date", "symbol"],
        "expected_fields": ["date", "symbol", "level", "level_name", "holders", "shares", "percentage"],
    },
]


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_returns_data_for_latest_row(case, client, engine):
    row = _sample_row(engine, case["table"], case["columns"])
    if not row:
        pytest.skip(f"no data in {case['table']}")

    params = {
        "start_date": row["date"],
        "end_date": row["date"],
        "limit": 5,
    }
    for key in case["params"]:
        params[key] = row[key]

    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "date" in data[0]
    assert DATE_RE.match(data[0]["date"])
    # Field completeness check (allow extra fields, but require expected ones)
    expected = set(case["expected_fields"])
    assert expected.issubset(set(data[0].keys()))


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_field_types(case, client, engine):
    row = _sample_row(engine, case["table"], case["columns"])
    if not row:
        pytest.skip(f"no data in {case['table']}")

    params = {
        "start_date": row["date"],
        "end_date": row["date"],
        "limit": 1,
    }
    for key in case["params"]:
        params[key] = row[key]

    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) >= 1
    record = data[0]

    for field in case["expected_fields"]:
        assert field in record
        val = record[field]

        if field == "date":
            assert isinstance(val, str)
            assert DATE_RE.match(val)
            continue

        if field in ("symbol", "market", "name", "direction", "institution", "item", "level_name", "bid", "ask"):
            assert val is None or isinstance(val, str)
            continue

        if field == "level":
            assert val is None or isinstance(val, int)
            continue

        # Numeric fields: int or float (or None)
        assert val is None or isinstance(val, (int, float))


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_limit_behavior(case, client, engine):
    row = _sample_row(engine, case["table"], case["columns"])
    if not row:
        pytest.skip(f"no data in {case['table']}")

    params = {
        "start_date": row["date"],
        "end_date": row["date"],
        "limit": 1,
    }
    for key in case["params"]:
        params[key] = row[key]

    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 1

    params["limit"] = 5
    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) <= 5


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_no_data_returns_empty(case, client):
    params = {
        "start_date": "2100-01-01",
        "end_date": "2100-01-01",
        "limit": 5,
    }
    if "symbol" in case["params"]:
        params["symbol"] = "ZZZZ"
    if "market" in case["params"]:
        params["market"] = "sii"

    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_start_date_after_end_date_returns_empty(case, client):
    params = {
        "start_date": "2026-12-31",
        "end_date": "2026-01-01",
        "limit": 5,
    }
    if "symbol" in case["params"]:
        params["symbol"] = "2330"
    if "market" in case["params"]:
        params["market"] = "sii"

    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_market_filter(case, client, engine):
    if "market" not in case["params"]:
        pytest.skip("endpoint has no market filter")

    row = _sample_row(engine, case["table"], case["columns"])
    if not row:
        pytest.skip(f"no data in {case['table']}")

    params = {
        "start_date": row["date"],
        "end_date": row["date"],
        "limit": 10,
        "market": row["market"],
    }
    if "symbol" in case["params"]:
        params["symbol"] = row["symbol"]

    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for rec in data:
        assert rec.get("market") == row["market"]


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_required_non_empty_fields(case, client, engine):
    row = _sample_row(engine, case["table"], case["columns"])
    if not row:
        pytest.skip(f"no data in {case['table']}")

    params = {
        "start_date": row["date"],
        "end_date": row["date"],
        "limit": 5,
    }
    for key in case["params"]:
        params[key] = row[key]

    resp = client.get(case["endpoint"], params=params)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list) and len(data) >= 1
    record = data[0]
    for field in case["required_non_empty"]:
        val = record.get(field)
        assert isinstance(val, str) and val.strip() != ""
