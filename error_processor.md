
## Processor Runtime Error - 2026-02-09 22:12:37
**Date:** 20230427
**Category:** institutional_summary
**Message:** Error in institutional_summary for sii: empty data from '/app/data/raw/institutional_summary/date=20230427/sii.csv'
**Traceback:**
```python
Traceback (most recent call last):
  File "/app/convert.py", line 72, in _handle_institutional_summary
    df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)
  File "/usr/local/lib/python3.10/site-packages/polars/_utils/deprecation.py", line 128, in wrapper
    return function(*args, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/polars/_utils/deprecation.py", line 128, in wrapper
    return function(*args, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/polars/_utils/deprecation.py", line 128, in wrapper
    return function(*args, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/polars/io/csv/functions.py", line 544, in read_csv
    with prepare_file_arg(
  File "/usr/local/lib/python3.10/site-packages/polars/io/_utils.py", line 272, in prepare_file_arg
    return _check_empty(
  File "/usr/local/lib/python3.10/site-packages/polars/io/_utils.py", line 291, in _check_empty
    raise NoDataError(msg)
polars.exceptions.NoDataError: empty data from '/app/data/raw/institutional_summary/date=20230427/sii.csv'

```
---

## Processor Runtime Error - 2026-02-09 22:12:38
**Date:** 20231024
**Category:** institutional_summary
**Message:** Error in institutional_summary for sii: empty data from '/app/data/raw/institutional_summary/date=20231024/sii.csv'
**Traceback:**
```python
Traceback (most recent call last):
  File "/app/convert.py", line 72, in _handle_institutional_summary
    df = pl.read_csv(file_path, encoding="utf-8-sig", infer_schema_length=0)
  File "/usr/local/lib/python3.10/site-packages/polars/_utils/deprecation.py", line 128, in wrapper
    return function(*args, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/polars/_utils/deprecation.py", line 128, in wrapper
    return function(*args, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/polars/_utils/deprecation.py", line 128, in wrapper
    return function(*args, **kwargs)
  File "/usr/local/lib/python3.10/site-packages/polars/io/csv/functions.py", line 544, in read_csv
    with prepare_file_arg(
  File "/usr/local/lib/python3.10/site-packages/polars/io/_utils.py", line 272, in prepare_file_arg
    return _check_empty(
  File "/usr/local/lib/python3.10/site-packages/polars/io/_utils.py", line 291, in _check_empty
    raise NoDataError(msg)
polars.exceptions.NoDataError: empty data from '/app/data/raw/institutional_summary/date=20231024/sii.csv'

```
---

## Data Quality Issues - 20230427
**Detected at:** 2026-02-09 22:13:05
**Issue count:** 2

- ❌ daily_quotes: Missing file data/processed/daily_quotes/date=20230427/sii.csv
- ❌ market_indices: Missing file data/processed/market_indices/date=20230427/sii.csv

**Action required:**
1. Check raw data files in `data/raw/*/date=20230427/`
2. Review processor logs for errors
3. Fix processor bugs if column mapping is incorrect
4. Re-run processor: `START_DATE=20230427 END_DATE=20230427 docker compose run --rm processor`

---
