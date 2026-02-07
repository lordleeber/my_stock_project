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
    },
    {
        "endpoint": "/raw/margin-trading",
        "table": "margin_trading",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
    },
    {
        "endpoint": "/raw/margin-summary",
        "table": "margin_summary",
        "columns": ["date", "market"],
        "params": ["market"],
    },
    {
        "endpoint": "/raw/institutional-investors",
        "table": "institutional_investors",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
    },
    {
        "endpoint": "/raw/institutional-summary",
        "table": "institutional_summary",
        "columns": ["date", "market"],
        "params": ["market"],
    },
    {
        "endpoint": "/raw/foreign-holding",
        "table": "foreign_holding",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
    },
    {
        "endpoint": "/raw/pe-ratio",
        "table": "pe_ratio",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
    },
    {
        "endpoint": "/raw/market-indices",
        "table": "market_indices",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
    },
    {
        "endpoint": "/raw/monthly-revenue",
        "table": "monthly_revenue",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
    },
    {
        "endpoint": "/raw/shareholding",
        "table": "shareholding_div",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
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
