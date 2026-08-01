# KNOWN_ISSUES.md

已確認、但尚未修復的問題。修好之後把該段整個刪掉,不要留「已解決」的殭屍條目。

---

## #1 — 2026Q2 XBRL raw 全是 MOPS 阻擋頁,且 scraper 永遠不會重抓

- **發現日期**:2026-08-01
- **狀態**:未修(重灌後處理)
- **影響**:`data/raw/xbrl/2026/2026Q2/` 無法使用;DB **未受污染**
- **緊急度**:中 —— DB 乾淨,但 2026Q2 一天不修就一天沒有季報資料,且不會自我修復

### 症狀

`data/raw/xbrl/2026/2026Q2/` 底下 1807 個 `.html`,其中 **1805 個是 800 bytes 的 MOPS 阻擋頁**,不是季報:

```
因為安全性考量,您所執行的頁面無法呈現。
FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED.
```

只有 2 個是真正的報表(正常報表約 500 KB 級)。**其他季別全部正常**:

| 季別 | 總數 | <2KB(阻擋頁) | >=2KB(正常) |
|---|--:|--:|--:|
| 2023Q3 ~ 2026Q1(11 季) | 1558–1653 | **0** | 全部 |
| 2026Q2 | 1807 | **1805** | 2 |

### 根因一:阻擋頁偵測有兩個「差一個字」的 marker

`scraper/quarterly/fetch_xbrl.py::detect_blocked_reason()`(約 line 90-102)對這個頁面回傳 `None`:

| 現有 marker | 頁面實際內容 | |
|---|---|---|
| `the page can not be accessed` | `this page can not be accessed` | `the` vs `this` |
| `頁面無法執行` | `頁面無法呈現` | `執行` vs `呈現` |

兩個都擦身而過,阻擋頁因此被當成正常回應存檔。

> 編碼不是原因。已驗證 `decode_to_utf8()` 對這些檔案正確 fallback 到 utf-8
> (該頁是 UTF-8,cp950/big5 都會 raise `UnicodeDecodeError` 而跳過)。

### 根因二:存檔後就永久 SKIP,不會自我修復

`load_existing_report_names()`(line 110-114)用 `strip_run_date_suffix()` 把檔名的
run_date 後綴剝掉,dedupe key 是 `YYYYQX_<symbol>.html`。於是 `save_symbol_report()`
(line 129)判定「已存在」→ 一律 SKIP:

```python
if not force and base_filename in existing_report_names:
    print(f"[SKIP] {symbol} -> skipped_exists ({base_filename})")
```

也就是說每天跑的 `schedules/xbrl_scrape_daily.sh` **永遠不會重抓 2026Q2**,除非帶
`--force` 或先把壞檔刪掉。錯一次就卡死。

### 血緣:DB 沒有被污染

```sql
SELECT count(*) FROM income_statement_xbrl WHERE date='2026Q2';  -- 0
SELECT count(*) FROM balance_sheet_xbrl    WHERE date='2026Q2';  -- 0
SELECT count(*) FROM cash_flow_xbrl        WHERE date='2026Q2';  -- 0
-- 對照 2026Q1:income_statement_xbrl = 108,546 列
```

因為 scrape 與 process+import 是分開的兩支(`xbrl_scrape_daily.sh` 只抓不入庫),
而 2026Q2 的 `xbrl_process_import.sh` 還沒跑過。髒資料停在 raw 層。

### 重灌相關

`data/raw` 的三份備份(Mac / NAS / 本機)內容一致,**都含這 1805 個壞檔** —— 備份忠實
反映來源,沒有問題。但重灌還原後這批壞檔會一起回來,scraper 仍會 SKIP。修這個 issue
與還原流程無關,可獨立進行。

### 建議修法

1. **放寬 marker**,避免再被冠詞/近義詞絆倒。至少加入:
   - `page can not be accessed`(去掉 `the`/`this` 前綴)
   - `頁面無法呈現`
   - 考慮改成「正向驗證」:報表頁應含特定 XBRL 結構,不含就視為失敗 —— 比逐條列舉
     阻擋訊息更難漏。
2. **加大小下限**:正常報表 ~500 KB,阻擋頁 800 bytes。`< 2 KB` 一律視為失敗,是
   便宜又有效的第二道防線。
3. **清掉壞檔後重抓**:
   ```bash
   # 先確認數量再刪
   find data/raw/xbrl/2026/2026Q2 -name '*.html' -size -2k | wc -l   # 應為 1805
   find data/raw/xbrl/2026/2026Q2 -name '*.html' -size -2k -delete
   docker compose build scraper-quarterly    # 改了 scraper/ 必須 rebuild
   docker compose run --rm scraper-quarterly \
       python3 scraper/quarterly/fetch_xbrl.py --year 2026 --quarter 2
   ```
   注意 MOPS 會因查詢過於頻繁而擋,重抓 1805 檔要留意速率(這很可能就是當初被擋的原因)。
4. **回頭驗證其他季別**:目前掃描顯示 2023Q3–2026Q1 全乾淨,但掃描條件只看檔案大小。
   marker 修好後值得對既有檔案重跑一次偵測,確認沒有其他型態的阻擋頁混在裡面。

### 驗證指令

```bash
# 各季別的阻擋頁數量
for d in data/raw/xbrl/*/*/; do
  find "$d" -name '*.html' -printf '%s\n' | awk -v q="$(basename "$d")" \
    '{t++; if($1<2000) s++} END {if(t) printf "%-8s total=%-6d bad=%d\n", q, t, s+0}'
done
```
