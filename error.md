# Data Quality Error Log

This file tracks data quality issues detected by `processor/data_quality_checker.py`.

Issues are automatically appended after each processor run.

---

## Data Quality Issues - 20260202
**Detected at:** 2026-02-07 03:50:21
**Issue count:** 11

- ❌ margin_trading sii: Column 'margin_long_buy' has 100.0% NULL values (1248/1248 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_sell' has 100.0% NULL values (1248/1248 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_balance' has 100.0% NULL values (1248/1248 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_buy' has 100.0% NULL values (1248/1248 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_sell' has 100.0% NULL values (1248/1248 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_balance' has 100.0% NULL values (1248/1248 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_balance' has 100.0% empty values (1253/1253 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_buy' has 100.0% empty values (1253/1253 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_sell' has 100.0% empty values (1253/1253 rows) - likely processor bug
- ❌ margin_sbl otc: Column 'margin_short_balance' has 100.0% empty values (898/898 rows) - likely processor bug
- ❌ institutional_investors otc: Column 'dealer_net' has 100.0% NULL values (894/894 rows)

**Action required:**
1. Check raw data files in `data/raw/*/date=20260202/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260202 END_DATE=20260202 docker compose run --rm processor`

---
