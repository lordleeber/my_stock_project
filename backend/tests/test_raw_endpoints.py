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
Q_DATE_RE = re.compile(r"^\d{4}Q[1-4]$")
M_DATE_RE = re.compile(r"^\d{4}M\d{2}$")


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
            "date",
            "symbol",
            "name",
            "market",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "value",
            "transactions",
            "change",
            "direction",
            "bid",
            "ask",
            "pe_ratio",
        ],
    },
    {
        "endpoint": "/raw/margin-trading",
        "table": "margin_trading",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "name",
            "margin_long_buy",
            "margin_long_sell",
            "margin_long_cash_repay",
            "margin_long_prev_balance",
            "margin_long_balance",
            "margin_long_limit",
            "margin_short_buy",
            "margin_short_sell",
            "margin_short_cash_repay",
            "margin_short_prev_balance",
            "margin_short_balance",
            "margin_short_limit",
            "offset_balance",
        ],
    },
    {
        "endpoint": "/raw/margin-summary",
        "table": "margin_summary",
        "columns": ["date", "market"],
        "params": ["market"],
        "required_non_empty": ["date", "market"],
        "expected_fields": [
            "date",
            "market",
            "item",
            "buy",
            "sell",
            "cash_repay",
            "prev_balance",
            "today_balance",
        ],
    },
    {
        "endpoint": "/raw/institutional-investors",
        "table": "institutional_investors",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "name",
            "foreign_buy",
            "foreign_sell",
            "foreign_net",
            "trust_buy",
            "trust_sell",
            "trust_net",
            "dealer_buy",
            "dealer_sell",
            "dealer_net",
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
            "date",
            "symbol",
            "market",
            "issued_shares",
            "foreign_investable_shares",
            "foreign_held_shares",
            "foreign_investable_ratio",
            "foreign_held_ratio",
            "foreign_legal_limit_ratio",
        ],
    },
    {
        "endpoint": "/raw/trust-holding",
        "table": "trust_holding",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "issued_shares",
            "trust_held_shares",
            "trust_held_ratio",
        ],
    },
    {
        "endpoint": "/raw/dealer-holding",
        "table": "dealer_holding",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "issued_shares",
            "dealer_held_shares",
            "dealer_held_ratio",
        ],
    },
    {
        "endpoint": "/raw/pe-ratio",
        "table": "pe_ratio",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "pe_ratio",
            "dividend_yield",
            "pb_ratio",
        ],
    },
    {
        "endpoint": "/raw/market-indices",
        "table": "market_indices",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "name",
            "market",
            "close",
            "change",
            "change_pct",
        ],
    },
    {
        "endpoint": "/raw/valuation-analysis",
        "table": "valuation_analysis",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
        "required_non_empty": ["date", "symbol"],
        "expected_fields": [
            "date",
            "symbol",
            "close",
            "ttm_eps",
            "pe_ratio_calculated",
            "pe_ratio_from_pe_table",
            "pe_percentile",
        ],
    },
    {
        "endpoint": "/raw/monthly-revenue",
        "table": "monthly_revenue",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "revenue_current",
            "revenue_last_month",
            "revenue_last_year",
            "mom_pct",
            "yoy_pct",
            "revenue_cumulative",
            "revenue_cumulative_last_year",
            "cumulative_yoy_pct",
            "publish_time",
        ],
        "is_q_format": True,
    },
    {
        "endpoint": "/raw/shareholding",
        "table": "shareholding",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
        "required_non_empty": ["date", "symbol"],
        "expected_fields": [
            "date",
            "symbol",
            "level",
            "level_name",
            "holders",
            "shares",
            "percentage",
        ],
    },
    {
        "endpoint": "/raw/shareholding-concentration",
        "table": "shareholding_concentration",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
        "required_non_empty": ["date", "symbol"],
        "expected_fields": [
            "date",
            "symbol",
            "large_holder_ratio",
            "small_holder_ratio",
            "concentration_spread",
            "large_holder_count",
            "small_holder_count",
            "large_holder_ratio_wow",
            "small_holder_ratio_wow",
            "concentration_spread_wow",
        ],
    },
    {
        "endpoint": "/raw/short-interest-analysis",
        "table": "short_interest_analysis",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "name",
            "sbl_balance",
            "sbl_balance_wow",
            "sbl_balance_wow_pct",
            "sbl_sell",
            "sbl_repay",
            "sbl_sell_repay_ratio",
            "margin_short_balance",
            "margin_short_balance_wow",
            "margin_short_balance_wow_pct",
            "short_pressure_score",
        ],
    },
    {
        "endpoint": "/raw/margin-pressure-analysis",
        "table": "margin_pressure_analysis",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "market",
            "name",
            "margin_long_balance",
            "margin_long_limit",
            "margin_usage_ratio",
            "margin_long_balance_wow",
            "margin_long_balance_wow_pct",
            "margin_short_balance",
            "margin_short_limit",
            "short_usage_ratio",
            "margin_short_balance_wow",
            "margin_short_balance_wow_pct",
            "short_cover_pressure",
            "margin_pressure_score",
        ],
    },
    {
        "endpoint": "/raw/quarterly-reports",
        "table": "quarterly_reports",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "name",
            "market",
            "revenue",
            "revenue_ly",
            "revenue_yoy",
            "eps",
            "eps_ly",
            "eps_yoy",
        ],
        "is_q_format": True,
    },
    {
        "endpoint": "/raw/income-statements",
        "table": "income_statement",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": ["date", "symbol", "revenue", "net_income", "eps"],
        "is_q_format": True,
    },
    {
        "endpoint": "/raw/balance-sheets",
        "table": "balance_sheet",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": [
            "date",
            "symbol",
            "total_assets",
            "total_equity",
            "nav_per_share",
        ],
        "is_q_format": True,
    },
    {
        "endpoint": "/raw/cash-flows",
        "table": "cash_flow",
        "columns": ["date", "symbol", "market"],
        "params": ["symbol", "market"],
        "required_non_empty": ["date", "symbol", "market"],
        "expected_fields": ["date", "symbol", "cash_flow_operating", "net_cash_change"],
        "is_q_format": True,
    },
    {
        "endpoint": "/raw/income-statements-xbrl",
        "table": "income_statement_xbrl",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
        "required_non_empty": [
            "date",
            "symbol",
            "period",
            "period_type",
            "account_code",
        ],
        "expected_fields": [
            "date",
            "symbol",
            "period",
            "period_type",
            "account_code",
            "account_name_cht",
            "account_name_eng",
            "value_text",
        ],
        "is_q_format": True,
    },
    {
        "endpoint": "/raw/balance-sheets-xbrl",
        "table": "balance_sheet_xbrl",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
        "required_non_empty": [
            "date",
            "symbol",
            "period",
            "period_type",
            "account_code",
        ],
        "expected_fields": [
            "date",
            "symbol",
            "period",
            "period_type",
            "account_code",
            "account_name_cht",
            "account_name_eng",
            "value_text",
        ],
        "is_q_format": True,
    },
    {
        "endpoint": "/raw/cash-flows-xbrl",
        "table": "cash_flow_xbrl",
        "columns": ["date", "symbol"],
        "params": ["symbol"],
        "required_non_empty": [
            "date",
            "symbol",
            "period",
            "period_type",
            "account_code",
        ],
        "expected_fields": [
            "date",
            "symbol",
            "period",
            "period_type",
            "account_code",
            "account_name_cht",
            "account_name_eng",
            "value_text",
        ],
        "is_q_format": True,
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

    # Date format check based on case type
    if case.get("is_q_format"):
        assert Q_DATE_RE.match(data[0]["date"]) or M_DATE_RE.match(data[0]["date"])
    else:
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
            if case.get("is_q_format"):
                assert Q_DATE_RE.match(val) or M_DATE_RE.match(val)
            else:
                assert DATE_RE.match(val)
            continue

        if field in (
            "symbol",
            "market",
            "name",
            "direction",
            "institution",
            "item",
            "level_name",
            "bid",
            "ask",
            "period",
            "period_type",
            "account_code",
            "account_name_cht",
            "account_name_eng",
            "value_text",
        ):
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
def test_raw_endpoint_offset_behavior(case, client, engine):
    """Verify that offset correctly shifts the result set."""
    # Fetch 2 rows with limit=2, offset=0
    start_date = "2020Q1" if case.get("is_q_format") else "2020-01-01"
    end_date = "2026Q4" if case.get("is_q_format") else "2026-12-31"

    params = {"start_date": start_date, "end_date": end_date, "limit": 2, "offset": 0}
    resp1 = client.get(case["endpoint"], params=params)
    assert resp1.status_code == 200
    data1 = resp1.json()

    if len(data1) < 2:
        pytest.skip(f"Not enough data in {case['table']} to test offset")

    # Fetch the 2nd row using limit=1, offset=1
    params["limit"] = 1
    params["offset"] = 1
    resp2 = client.get(case["endpoint"], params=params)
    assert resp2.status_code == 200
    data2 = resp2.json()

    assert len(data2) == 1
    # The record at offset 1 should match the 2nd record from the first request
    assert data2[0] == data1[1]


@pytest.mark.parametrize("case", CASES)
def test_raw_endpoint_no_data_returns_empty(case, client):
    params = {
        "start_date": "2100Q1" if case.get("is_q_format") else "2100-01-01",
        "end_date": "2100Q1" if case.get("is_q_format") else "2100-01-01",
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
        "start_date": "2026Q4" if case.get("is_q_format") else "2026-12-31",
        "end_date": "2026Q1" if case.get("is_q_format") else "2026-01-01",
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


XBRL_ENDPOINT_CASES = [
    ("income_statement_xbrl", "/raw/income-statements-xbrl"),
    ("balance_sheet_xbrl", "/raw/balance-sheets-xbrl"),
    ("cash_flow_xbrl", "/raw/cash-flows-xbrl"),
]


@pytest.mark.parametrize("table,endpoint", XBRL_ENDPOINT_CASES)
def test_xbrl_endpoint_returns_rows(table, endpoint, client, engine):
    row = _sample_row(engine, table, ["date", "symbol"])
    if not row:
        pytest.skip(f"no data in {table}")

    resp = client.get(
        endpoint,
        params={
            "start_date": row["date"],
            "end_date": row["date"],
            "symbol": row["symbol"],
            "limit": 3,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    record = data[0]
    expected_fields = {
        "date",
        "symbol",
        "period",
        "period_type",
        "account_code",
        "account_name_cht",
        "account_name_eng",
        "value_text",
    }
    assert expected_fields.issubset(set(record.keys()))
    assert "value_num" not in record
    assert isinstance(record["date"], str) and Q_DATE_RE.match(record["date"])
    assert isinstance(record["symbol"], str) and record["symbol"].strip() != ""


@pytest.mark.parametrize("endpoint", [item[1] for item in XBRL_ENDPOINT_CASES])
def test_xbrl_endpoint_rejects_bad_date(endpoint, client):
    resp = client.get(
        endpoint,
        params={
            "start_date": "2025-01-01",
            "end_date": "2025Q1",
            "limit": 1,
        },
    )
    assert resp.status_code == 400
