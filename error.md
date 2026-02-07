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

## Data Quality Issues - 20260202
**Detected at:** 2026-02-07 03:54:00
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

## Data Quality Issues - 20260130
**Detected at:** 2026-02-07 04:05:29
**Issue count:** 11

- ❌ margin_trading sii: Column 'margin_long_buy' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_sell' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_balance' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_buy' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_sell' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_balance' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_balance' has 100.0% empty values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_buy' has 100.0% empty values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_sell' has 100.0% empty values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl otc: Column 'margin_short_balance' has 100.0% empty values (897/897 rows) - likely processor bug
- ❌ institutional_investors otc: Column 'dealer_net' has 100.0% NULL values (886/886 rows)

**Action required:**
1. Check raw data files in `data/raw/*/date=20260130/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260130 END_DATE=20260130 docker compose run --rm processor`

---

## Data Quality Issues - 20260130
**Detected at:** 2026-02-07 04:09:29
**Issue count:** 11

- ❌ margin_trading sii: Column 'margin_long_buy' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_sell' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_balance' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_buy' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_sell' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_balance' has 100.0% NULL values (1246/1246 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_balance' has 100.0% empty values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_buy' has 100.0% empty values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_sell' has 100.0% empty values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl otc: Column 'margin_short_balance' has 100.0% empty values (897/897 rows) - likely processor bug
- ❌ institutional_investors otc: Column 'dealer_net' has 100.0% NULL values (886/886 rows)

**Action required:**
1. Check raw data files in `data/raw/*/date=20260130/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260130 END_DATE=20260130 docker compose run --rm processor`

---

## Data Quality Issues - 20260130
**Detected at:** 2026-02-07 04:10:48
**Issue count:** 3

- ❌ margin_sbl otc: Column 'margin_short_balance' has 100.0% empty values (897/897 rows) - likely processor bug
- ❌ margin_sbl otc: Column 'margin_short_buy' has 100.0% empty values (897/897 rows) - likely processor bug
- ❌ margin_sbl otc: Column 'margin_short_sell' has 100.0% empty values (897/897 rows) - likely processor bug

**Action required:**
1. Check raw data files in `data/raw/*/date=20260130/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260130 END_DATE=20260130 docker compose run --rm processor`

---

## Data Quality Issues - 20260202
**Detected at:** 2026-02-07 04:16:54
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

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 04:17:45
**Issue count:** 11

- ❌ margin_trading sii: Column 'margin_long_buy' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_sell' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_balance' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_buy' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_sell' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_balance' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_balance' has 100.0% empty values (1256/1256 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_buy' has 100.0% empty values (1256/1256 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_sell' has 100.0% empty values (1256/1256 rows) - likely processor bug
- ❌ margin_sbl otc: Column 'margin_short_balance' has 100.0% empty values (899/899 rows) - likely processor bug
- ❌ institutional_investors otc: Column 'dealer_net' has 100.0% NULL values (885/885 rows)

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 04:17:51
**Issue count:** 11

- ❌ margin_trading sii: Column 'margin_long_buy' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_sell' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_long_balance' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_buy' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_sell' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_trading sii: Column 'margin_short_balance' has 100.0% NULL values (1251/1251 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_balance' has 100.0% empty values (1256/1256 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_buy' has 100.0% empty values (1256/1256 rows) - likely processor bug
- ❌ margin_sbl sii: Column 'margin_short_sell' has 100.0% empty values (1256/1256 rows) - likely processor bug
- ❌ margin_sbl otc: Column 'margin_short_balance' has 100.0% empty values (899/899 rows) - likely processor bug
- ❌ institutional_investors otc: Column 'dealer_net' has 100.0% NULL values (885/885 rows)

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260202
**Detected at:** 2026-02-07 04:21:52
**Issue count:** 12

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
- ❌ market_indices: Missing file data/processed/market_indices/date=20260202/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260202/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260202 END_DATE=20260202 docker compose run --rm processor`

---

## Data Quality Issues - 20260202
**Detected at:** 2026-02-07 04:22:06
**Issue count:** 12

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
- ❌ market_indices: Missing file data/processed/market_indices/date=20260202/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260202/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260202 END_DATE=20260202 docker compose run --rm processor`

---

## Data Quality Issues - 20260202
**Detected at:** 2026-02-07 04:30:10
**Issue count:** 2

- ❌ market_indices: Missing file data/processed/market_indices/date=20260202/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260202/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260202/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260202 END_DATE=20260202 docker compose run --rm processor`

---

## Data Quality Issues - 20260203
**Detected at:** 2026-02-07 04:30:11
**Issue count:** 2

- ❌ market_indices: Missing file data/processed/market_indices/date=20260203/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260203/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260203/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260203 END_DATE=20260203 docker compose run --rm processor`

---

## Data Quality Issues - 20260204
**Detected at:** 2026-02-07 04:30:11
**Issue count:** 2

- ❌ market_indices: Missing file data/processed/market_indices/date=20260204/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260204/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260204/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260204 END_DATE=20260204 docker compose run --rm processor`

---

## Data Quality Issues - 20260205
**Detected at:** 2026-02-07 04:30:12
**Issue count:** 2

- ❌ market_indices: Missing file data/processed/market_indices/date=20260205/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260205/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260205/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260205 END_DATE=20260205 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 04:30:12
**Issue count:** 2

- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260206/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 04:52:42
**Issue count:** 15

- ❌ margin_trading: Missing file data/processed/margin_trading/date=20260206/sii.csv
- ❌ margin_trading: Missing file data/processed/margin_trading/date=20260206/otc.csv
- ❌ margin_sbl: Missing file data/processed/margin_sbl/date=20260206/sii.csv
- ❌ margin_sbl: Missing file data/processed/margin_sbl/date=20260206/otc.csv
- ❌ daily_quotes: Missing file data/processed/daily_quotes/date=20260206/sii.csv
- ❌ daily_quotes: Missing file data/processed/daily_quotes/date=20260206/otc.csv
- ❌ institutional_investors: Missing file data/processed/institutional_investors/date=20260206/sii.csv
- ❌ institutional_investors: Missing file data/processed/institutional_investors/date=20260206/otc.csv
- ❌ foreign_holding: Missing file data/processed/foreign_holding/date=20260206/sii.csv
- ❌ foreign_holding: Missing file data/processed/foreign_holding/date=20260206/otc.csv
- ❌ pe_ratio: Missing file data/processed/pe_ratio/date=20260206/sii.csv
- ❌ pe_ratio: Missing file data/processed/pe_ratio/date=20260206/otc.csv
- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/sii.csv
- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260206/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 04:53:29
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 06:08:17
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 06:12:18
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 06:36:16
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 06:36:35
**Issue count:** 2

- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260206/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 06:38:04
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260206/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260206
**Detected at:** 2026-02-07 06:39:04
**Issue count:** 5

- ❌ daily_quotes sii: Column 'open' has 100.0% NULL values (1650/1650 rows) - check if market was open
- ❌ daily_quotes sii: Column 'high' has 100.0% NULL values (1650/1650 rows) - check if market was open
- ❌ daily_quotes sii: Column 'low' has 100.0% NULL values (1650/1650 rows) - check if market was open
- ❌ daily_quotes sii: Column 'close' has 82.6% NULL values (1363/1650 rows) - check if market was open
- ❌ daily_quotes sii: Column 'volume' has 100.0% NULL values (1650/1650 rows) - check if market was open

**Action required:**
1. Check raw data files in `data/raw/*/date=20260206/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260206 END_DATE=20260206 docker compose run --rm processor`

---

## Data Quality Issues - 20260130
**Detected at:** 2026-02-07 06:43:15
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260130/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260130/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260130 END_DATE=20260130 docker compose run --rm processor`

---

## Data Quality Issues - 20260202
**Detected at:** 2026-02-07 06:47:38
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260202/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260202/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260202 END_DATE=20260202 docker compose run --rm processor`

---

## Data Quality Issues - 20260203
**Detected at:** 2026-02-07 06:47:38
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260203/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260203/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260203 END_DATE=20260203 docker compose run --rm processor`

---

## Data Quality Issues - 20260204
**Detected at:** 2026-02-07 06:47:39
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260204/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260204/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260204 END_DATE=20260204 docker compose run --rm processor`

---

## Data Quality Issues - 20260205
**Detected at:** 2026-02-07 06:47:39
**Issue count:** 1

- ❌ market_indices: Missing file data/processed/market_indices/date=20260205/otc.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260205/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260205 END_DATE=20260205 docker compose run --rm processor`

---

## Data Quality Issues - 20260207
**Detected at:** 2026-02-07 13:00:07
**Issue count:** 15

- ❌ margin_trading: Missing file data/processed/margin_trading/date=20260207/sii.csv
- ❌ margin_trading: Missing file data/processed/margin_trading/date=20260207/otc.csv
- ❌ margin_sbl: Missing file data/processed/margin_sbl/date=20260207/sii.csv
- ❌ margin_sbl: Missing file data/processed/margin_sbl/date=20260207/otc.csv
- ❌ daily_quotes: Missing file data/processed/daily_quotes/date=20260207/sii.csv
- ❌ daily_quotes: Missing file data/processed/daily_quotes/date=20260207/otc.csv
- ❌ institutional_investors: Missing file data/processed/institutional_investors/date=20260207/sii.csv
- ❌ institutional_investors: Missing file data/processed/institutional_investors/date=20260207/otc.csv
- ❌ foreign_holding: Missing file data/processed/foreign_holding/date=20260207/sii.csv
- ❌ foreign_holding: Missing file data/processed/foreign_holding/date=20260207/otc.csv
- ❌ pe_ratio: Missing file data/processed/pe_ratio/date=20260207/sii.csv
- ❌ pe_ratio: Missing file data/processed/pe_ratio/date=20260207/otc.csv
- ❌ market_indices: Missing file data/processed/market_indices/date=20260207/sii.csv
- ❌ market_indices: Missing file data/processed/market_indices/date=20260207/otc.csv
- ❌ institutional_summary: Missing file data/processed/institutional_summary/date=20260207/all.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20260207/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20260207 END_DATE=20260207 docker compose run --rm processor`

---
