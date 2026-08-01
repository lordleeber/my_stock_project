# DIAG：2026-07 颱風遲報營收的 look-ahead 診斷

> ⚠️ **這不是生產名單,不可拿來下單。** 本目錄的生產名單一律是 `candidates_scored.csv`。
> 本檔描述的 `*.DIAG_lookahead_rev0713.csv` 刻意使用了 2026-07-11 當下拿不到的資料,
> 只用於量化颱風影響,任何流程都不會讀它(所有消費者抓的是精確檔名 `candidates_scored.csv`)。

## 背景

2026-07-10(原訂 6 月營收公告截止日 = playbook cutoff)因颱風臨時停市停班,
2026M06 共 1838 筆申報中有 **192 筆遲報**(181 筆落在 07-13、7 筆 07-14、3 筆 07-12、1 筆 07-11)。
生產名單於 2026-07-11 15:52 產出時,這 192 筆被 `publish_time <= 20260710` 的 PIT 過濾擋掉,
遲報者的營收特徵**回退用 2026M05**。

## 實驗設計

在隔離 worktree 中把三條營收路徑的 gate 統一綁到一個 `DIAG_REV_CUTOFF` 環境變數,
技術面特徵 pin 在 cutoff(避免 7/09→7/13 的價量漂移混入),只變動營收 cap:

| Mode | 營收 cap | 用途 |
|---|---|---|
| A | `<= 20260710` | 對照組(重現凍結名單) |
| B | `<= 20260713` | 納入遲報營收(← 本檔) |

其餘條件不變:walk-forward 模型固定用 `models_selection/2026-06-11/selection_model.pkl`
(K=10 ensemble, seeds 42-51, agg=score),entry_date 2026-07-13,候選池 359 檔。

## 對照組驗證

Mode A 產出與生產 `candidates_scored.csv` **逐 byte 相同**(md5 `3aa61c905ebea4d7752abb4858c8a68b`),
EPS `pred_lgb_delta` 783 列 max|Δ|=0。因此 A/B 差異可 100% 歸因於那 192 筆遲報營收。
(Mode A 與生產檔重複,故未留存。)

## 結果:top-25 只換一名(24/25 重疊)

| 代號 | 名稱 | frozen rank | DIAG rank | 變化 |
|---|---|---|---|---|
| 6727 | 亞泰金屬 | 18 | 27 | 掉出 |
| 3037 | 欣興 | 26 | 25 | 進榜 |

6727 掉出的成因(2026M06 於 20260713 才公告):

| 期別 | 營收(仟元) | YoY | 公告日 |
|---|---|---|---|
| 2026M05 | 195,867 | **+54.10%** | 20260611 ← frozen 用這筆 |
| 2026M06 | 141,495 | **−23.89%**(MoM −27.75%) | 20260713 |

連續數月 +30~+54% 後首度翻負,導致 Δrevenue_yoy_1m −77.99、Δrevenue_yoy_accel −98.51、
Δml_eps_delta_pct −3.91。

## 結論

颱風造成的名單污染**侷限在單一檔**(6727,frozen rank 18)。359 檔候選池中有 26 檔遲報者,
其餘 25 檔最佳排名僅 85,離 top-25 甚遠。生產名單維持凍結不動。

## 檔案

| 檔案 | 內容 |
|---|---|
| `candidates_scored.DIAG_lookahead_rev0713.csv` | Mode B 候選評分(359 列) |
| `predictions_results.DIAG_lookahead_rev0713.csv` | Mode B 對應的 EPS 預測 |

產出日期:2026-07-15。
