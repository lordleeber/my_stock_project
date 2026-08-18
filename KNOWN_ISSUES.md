# KNOWN_ISSUES.md

已確認、但尚未修復的問題。修好之後把該段整個刪掉,不要留「已解決」的殭屍條目。

---

## 金融類股不在資料與選股範圍內（刻意的，不打算修）

`processor/quarterly/convert_xbrl.py` 只認一般行業的 TIFRS 科目表，金融業（金控/銀行/
保險）用的是另一套，整份報表解析不出任何一列 —— 五季實測 raw 有 11~13 檔金控、
`quarterly_reports_xbrl` 0 檔。step1 從該表起手，所以金融股也不會進選股宇宙。

記在這裡只為兩件事：別把它當 bug 去修；`schedules/xbrl_scrape_daily.sh` 的窗口也
**不需要**為金融業較晚的申報期限（Q1/Q3 5/30、半年報 8/31）往後延。

---

## `quarterly_reports_xbrl` 的 12 個 `*_acc_ly` / `*_acc_yoy` 欄位全表 NULL

`processor/quarterly/convert_quarterly_reports_xbrl.py::build_experiment_row` 裡：

```python
prev_inc_a, _ = read_wide_code_map(prev_inc_a_path, symbol)
```

`read_wide_code_map()` 回傳的是 **dict**，這行卻拿它解包成兩個變數。實務上損益表寬列
的科目數不會剛好是 2，所以解包幾乎總是拋 `ValueError: too many values to unpack`，
被下一行的 `except ValueError: prev_inc_a = {}` 接掉 —— `prev_inc_a` 留在空 dict，
去年同季的基準取不到。

同一個 `except` 還吃掉另一條正常路徑：symbol 不在去年同季檔案裡時，
`read_wide_code_map()` 自己就拋 `ValueError`。另有一個未被接到的邊角 —— 萬一科目
剛好 2 個，解包會「成功」讓 `prev_inc_a` 變成一個科目**字串**，之後 `.get()` 拋
`AttributeError`，該檔會被 `main()` 的廣義 handler 整個丟出該季。

實測（2026-08-16）：全部 26 季 × 兩種 `period_type`，以下 12 欄 100% NULL。

```
revenue_acc_ly / revenue_acc_yoy          op_income_acc_ly / op_income_acc_yoy
non_op_income_acc_ly / non_op_income_acc_yoy   pretax_income_acc_ly / pretax_income_acc_yoy
net_income_acc_ly / net_income_acc_yoy    eps_acc_ly / eps_acc_yoy
```

`BACKFILL_QUARTERS`（2020Q1~Q4）本來要從舊版 `quarterly_reports` 補，但那張表與它的
processed CSV 都已隨舊季報流程 deprecated 掉，所以連那四季也是空的。

**下游影響**：`strategies/step1_prepare_data.py:163` 把 `eps_acc_yoy` 與
`revenue_acc_yoy` 當特徵撈進 dataset —— 這兩個特徵目前恆為 NULL，等於沒作用。

沒有在修個體財報的 PR 裡一併處理，是因為修它會同時改動 12 個欄位的值與 2 個 ML
特徵，必須連帶重跑選股模型與回測驗證，跟「報表別判讀」是兩件事。修的時候注意：
轉換戶去年同季的報表別可能與本季不同（合併 ↔ 個體），`net_income_acc_ly` 取哪個
科目要依**該季自己的** `report_category` 決定，不能沿用本季的。

---

## 報表別轉換戶在轉換季有記帳基礎斷裂（11 檔，刻意不修）

公司有子公司時申報合併（`REPORT_ID=C`），子公司清算或處分完就改申報個體（`A`）；
反過來取得子公司則從個體轉合併。轉換季前後兩列在 `quarterly_reports_xbrl` 裡是
**不同記帳基礎**，跨該季的比較（YoY / QoQ）在概念上不成立。

### 盤點（2026-08-17，2020Q1~2026Q2 共 45,324 份 raw）

```
全期合併  1,599 檔      單次 C→A（轉個體）  32 檔
全期個體    141 檔      單次 A→C（轉合併）  75 檔
期間有變動  117 檔      來回切換 >1 次      10 檔
```

### 量測方法

拿**新報表裡的去年同期比較數**（已重編到新基礎）對上**去年那份報表自己的原值**。
兩者期間完全相同，所以差異只可能來自記帳基礎，不含營運變化。

### 結果：C→A 幾乎沒有落差

36 檔可比對（2816 兩邊都缺值），**營收 `4000` 與淨利（個體 `8200` / 合併 `8610`）
36/36 逐元相等**；逐科目完全相符的有 20/37。轉個體的公司，子公司本來就沒有實質
營運 —— 2007 是典型：88 個共同科目只有 2 個不同，而且是 2,942k 關係人應付款從
`2220` 併回 `2200` 的重分類。

淨利基礎不變是制度保證的（個體本期淨利 ≡ 合併歸屬母公司淨利），這同時反向驗證了
`NET_INCOME_CODE_BY_REPORT_CATEGORY` 的 `8200 ↔ 8610` 對映。

### 結果：A→C 才是有斷裂的方向

66 檔可比對，**57 檔逐欄相等，9 檔有差**。以下是全部 11 檔受影響清單
（百分比為新基礎相對舊基礎）：

| 代號 | 邊界 | 方向 | 落差 |
|---|---|---|---|
| 2432 | 2020Q4→2021Q4 | A→C | 營收 +431.7%；總資產 +79.1%；流動負債 +229.9%；權益 +25.9% |
| 5348 | 2022Q2→2023Q2 | A→C | 營收 +78.9%；營益 +1244.5%；總資產 +37.8%；流動負債 +188.9% |
| 8432 | 2022Q4→2023Q4 | A→C | 營收 +59.6%；總資產 +24.3%；流動負債 +149.1%；權益 +13.6% |
| 6684 | 2022Q2→2023Q2 | A→C | 營益 −57.4%；淨利 −54.3%；總資產 −30.5%；權益 −24.2%（追溯重編，非併購） |
| 7714 | 2022Q4→2023Q4 | A→C | 權益 +14.7%；總資產 +5.0%；其餘 <1% |
| 7722 | 2022Q4→2023Q4 | A→C | 營收 +6.7%；總資產 +3.6%；其餘 <2% |
| 4413 | 2022Q1→2023Q1 | A→C | 流動負債 +1.4%；其餘 <0.3% |
| 7631 | 2023Q2→2024Q2 | A→C | 全欄 <1% |
| 8227 | 2025Q1→2026Q1 | A→C | 流動資產 −0.4% |
| 1465 | 2020Q3→2021Q3 | C→A | 流動資產 −36.2%（非流動 +20.1%）；**總資產只差 −0.003%** |
| 1524 | 2023Q1→2024Q1 | C→A | 營益 +0.1% |

1465 表面上 26 科不符，但總資產只差 54k / 19.3 億 —— 是 2.49 億在流動/非流動之間
換位，子公司的流動資產在個體報表變成一筆非流動的「採用權益法之投資」。

### 下游影響

`strategies/step1_prepare_data.py` 的跨季特徵中：

- **EPS 系全部免疫** —— `anchor_yoy_eps` / `ly_seasonality` / `ttm_eps` / `delta_eps`
  都建在 `eps_q` 上，EPS 與淨利基礎不變
- `anchor_margin` / `margin_momentum`（用 `revenue_q`）、`anchor_roe`（用權益）、
  `anchor_debt_ratio`（用總資產負債）—— 受上表 9 檔 A→C 影響
- `current_ratio` / `quick_ratio` —— 只有 1465 一檔

暴露面約 11 檔 × 各 1 個邊界，相對 ~1,795 檔的宇宙是 0.5% 量級，而且是**一次性
水位跳動、不是持續性錯誤**：兩邊在各自基礎上都是正確的，只有跨邊界比較沒有意義。

### 為什麼不修

加排除規則會引入 look-ahead —— 轉換發生在未來，在 playbook date 當下不可知。硬把
轉換季標成 NULL 需要「未來會轉換」這個資訊。相對於這次要修的「宇宙少了 165 檔
（10%）」，斷裂幅度與影響面都低兩個數量級。

回測若在這幾檔上看到異常，再回頭處理。重跑盤點的腳本邏輯：對每個 symbol 從 raw
的 `tifrs-notes:ReportCategory` 建季度時間軸，找 `C→A` / `A→C` 邊界，再比對新報表
的去年同期 `contextRef` 與去年那份報表的當期值。

### 附帶發現：EPS 比較數會被追溯重編

C→A 的 36 檔裡有 4 檔 EPS 比較數對不上（8077 差 5 倍、6903、8028、6144），但**淨利
逐元相等** —— 差的是加權平均股數：8077 是減資、6903 是配股，依規定追溯重編。這與
報表別無關，合併對合併之間一樣會發生。

實務上不影響現況：`eps_acc_ly` 走 `prev_inc_a`（讀去年那份檔案自己的值），不讀比較
數欄。但修上一節的 `prev_inc_a` bug 時**不要**改成去讀本季報表的比較數欄 —— 那會
讓 `*_acc_ly` 帶上追溯重編，與 `*_acc` 的口徑不一致。

---

## 重跑歷史 playbook date 時，train_eps 會把「當年標籤」吃進訓練集

`train_eps/step1_prepare_data.py:700` 切 `dataset_train` 的條件只有「`target_eps`
非空」，沒有「標籤的公告日 ≤ 該 playbook 的 cutoff」這道過濾。PIT 是**靠環境隱含
達成**的 —— 跑的當下 DB 裡本來就還沒有那一季。:445 的註解把這個假設寫得很清楚：

```
-- target_q（如 2026Q2）公告日尚未到時，target_eps 自然 NaN，這是 live prediction
```

所以 **live 跑沒問題，重跑歷史日期就會外洩**。重建 2025-08-16 時，DB 裡
2025Q3 早就有了，於是 `(2025, 2025Q2)` 那 803 列帶著 2025Q3 的真實 EPS 進了訓練集
—— 而那 803 列正是這個 playbook 要預測的 live 列（evaluate 有 807 列，其中 803 列
有標籤）。**模型訓練在它要預測的那批列上。**

### 量測（2026-08-18，個體財報重建後）

`models_eps/<date>/predictions_results.csv` 在 live 年份上的誤差，對上同一份
`evaluate_by_fold.json` 裡 `expanding_by_year` 協定同一年的 CV 誤差：

| playbook date | live 年 | 已發布預測 MAE | walk-forward CV MAE | baseline |
|---|---|---|---|---|
| 2023-08-16 | 2023 | 0.308 | 0.54 | 0.60 |
| 2024-08-16 | 2024 | 0.403 | 0.64 | 0.65 |
| 2025-08-16 | 2025 | 0.522 | 0.89 | 1.10 |
| 2026-08-16 | 2026 | — | — | — |

重建出來的預測比誠實的 walk-forward 準 **37~43%**。2026-08-16 那列 `y_true` 全空
（2026Q3 要 11/14 才公告），是唯一乾淨的 live cohort，也反證了機制。

注意 step3 的評估本身是乾淨的：`evaluate_by_fold.json` 走 `expanding_by_year`。
髒的是 step2 訓練的**生產模型**（吃整份 `dataset_train`）與 step4 據此發布的
`predictions_results.csv` —— 而後者才是 `strategies/step1_prepare_data.py` 讀的。

### 影響範圍

- **每月正式流程不受影響**：真正的 playbook date 當下 target 季還沒公告，
  `target_eps` 是 NaN，進不了 `dataset_train`。
- **回測曲線帶樂觀**：全部歷史 cohort 的 EPS 特徵都是這樣產的，經
  `strategies` → `models_selection` → `backtester/output/rolling/` 一路傳下去。
- **新舊對照仍然有效**：2026-05/06 那次 ensemble 重建與 2026-08-18 的個體財報
  重建，兩邊用同一套流程，污染條件相同，差異可以歸因到宇宙擴大本身。

### 修法與代價

在 `dataset_train` 的 labeled_mask 上加一條「target 季的法定公告日 ≤ 該 playbook
的 cutoff_date」。等於歷史 cohort 的訓練集各少掉最後一年（約 18%，2025-08-16 是
803/4456），全部 61 個 EPS 模型與下游 selection model、回測都要重跑，`~0.74` 的
Sharpe 基準必然下修。屬於獨立議題，不要混進資料面的修補一起做。

---

## `shareholding` 的 2026-07-09 是部分快照（1849 檔，其他日期 ~2952）

那一週的 TDCC 快照原本整份漏掉（7/10 週五休市 → 基準日順延到週四 → 7/12 沒抓到 →
7/19 抓到的已是 7/17），**已於 2026-08-10 回補入庫**。但回補只能逐檔爬歷史查詢頁
（TDCC OpenData 沒有歷史），股票清單用 `active_stocks.txt` 的 1849 檔，所以這一天
**永遠會比鄰近日期少約 1100 檔**：

```
2026-07-03  2952
2026-07-09  1849   ← 回補，部分快照
2026-07-17  2955
```

殘留影響只有一處：那 ~1100 檔沒補到的股票，它們 **2026-07-17 那列的 `*_wow` 仍是
14 天差分冒充週差分**（LAG 跳過 07-09 直接接到 07-03）。有補到的 1849 檔已是正確的
週差分。實測沒有任何 cohort 的 top-2 會讀到 07-17 那列，所以目前無下游影響。

受影響的 **cohort 2026-07-11（cutoff 07-10）已確認完全修復**：359 檔全部在 07-09
有 concentration，`step1` 取到的最新兩筆從錯誤的 `07-03 + 06-26` 回到正確的
`07-09 + 07-03`。

回補流程記在 `scraper/weekly/merge_shareholding.py` 的 docstring（fetch → merge →
convert → import → `--force-full`）。漏抓機制本身已於 2026-08-08 修掉，見
`scraper/weekly/check_outputs.py` 的新鮮度 + 連續性 gate。
