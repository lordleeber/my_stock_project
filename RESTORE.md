# RESTORE.md — 重灌後從 Mac 還原

從全新的 Ubuntu 24.04 還原整套環境。備份來源是 Mac(`poyilee@172.16.4.90`),
於 **2026-08-01** 建立並逐項校驗過。

> 本文件只描述「還原」。日常作業流程見 [`MONTHLY_PLAYBOOK.md`](MONTHLY_PLAYBOOK.md),
> 架構說明見 [`CLAUDE.md`](CLAUDE.md)。

## 狀態:2026-08-01 的重灌還原已完成

那次還原已依本文件執行完畢並驗證通過(dump md5 相符、§4.3 四項列數全中、
`data/raw` 與 Mac 逐檔比對 0 缺漏、模型 50/61 目錄、6 個 timer + linger)。
**本文件自此不是待辦清單,而是下一次硬碟故障或換機器時的災難復原手冊**,
同時保存 2026-08-01 的實測基準——那組數字是備份當下的快照,事後無法回溯重測。

### 實際跑過一次之後發現的四處落差(1–3 尚未修正,4 已於 2026-08-08 修正)

1. **§10 的驗收指令跑不起來,且逐行相同這個條件本身不可能達成。**
   step5 需要 `strategies/output/<date>/dataset_strategy.csv`,但它被 `.gitignore`
   的 `*.csv` 忽略,也不在 `backup_ubuntu_20260801/` 裡,§1–§9 沒有任何一步會產生它。
   就算改用 step1 → step2 從 DB 重生,`step2_finalize_strategy.py` 的技術指標與
   營收特徵都是取「≤ `entry_date` 的最新一筆」——正式執行時 entry_date 尚未到來,
   DB 物理上沒有那天的資料所以 PIT 正確;歷史重跑時 DB 早已涵蓋 entry_date,
   特徵就整組往後位移。2026-07-11 這個 cohort 實測:技術面 355–359 檔全變
   (2344 的 ma5 由 07-09 的 177.3 變成 07-13 的 173.8),營收 26 檔遲報者變動。
   **這不代表還原失敗。** 改用對時間穩健的判準即可:step1 的 symbol 集合逐一相同、
   EPS 路徑特徵 `max|Δ| = 0`、XBRL/籌碼/估值特徵零差異——2026-08-01 這三項全過。
2. **§5 的 rsync 會靜默回退 git 追蹤的檔案。**
   `models_selection/` 底下有 3 個追蹤中的 `.md`(其餘 `.csv`/`.json`/`.pkl` 都被
   gitignore)。備份快照建立於 12:11,而 PR #15 於 13:00 才 merge,所以備份裡是
   舊版 `feature_analysis.md`,rsync 會把已 merge 的版本蓋掉。§5 的驗收只數目錄數
   與檔案數,抓不到內容錯誤。跑完 §5 請加跑 `git status --short`(應為空),
   有異動就 `git restore models_selection/ models_eps/`。加 `--exclude='*.md'`
   可根本避免。
3. **§2 少了 git identity。** 全新機器沒有 `~/.gitconfig`,第一次 commit 會以
   `Author identity unknown` 失敗。不影響還原本身,所以要到數天後才發作:
   `git config user.name "poyi"` / `git config user.email "poyilee1030@gmail.com"`
   (設 local 即可)。另外 §1 的套件清單沒有 `gh`,PR 流程會用到。
4. **§2 少了「先 touch 出 error log 檔」,結果三個檔案被 docker 建成 root 目錄。**
   2026-08-01 17:47 實際發生:`error_processor.log`、`error_importer.log`、
   `error_calculator.log` 全變成 `drwxr-xr-x root root`,`write_error_report()`
   從此固定拋 `IsADirectoryError`。因為壞的是錯誤處理器,交易日一路正常,
   直到 2026-08-08 查資料完整性時才從 8/1、8/2 兩份 log 的 traceback 發現。
   資料沒受影響(pipeline 仍會非零退出擋住污染),但各腳本叫你去看的那份
   error log 永遠是空的。已補 §2 的 touch 步驟。
   同時發現 `docker-compose.yml` 從一開始就漏了兩個 mount:4 個 scraper service
   的 `error_scraper.log`、calculator 的 `error_valuation_calculator.log`——
   內容一直隨 `--rm` 消失(2026Q2 那 9 筆 `invalid_report:too_small` 就查不到了),
   一併補上。現在程式碼裡的 5 個路徑與 compose mount 一一對應。

   §2 的 touch 步驟靠人記得照做,所以另外補了兩層不依賴人的防線:
   - `schedules/ensure_error_logs.sh`:每支會跑 `docker compose` 的排程腳本
     開頭都會呼叫它,自動 touch 出這 5 個檔;已經變成目錄時印出明確的
     `sudo rmdir` 指令並回非 0(rmdir 要 root,不自己修)。
   - `common/error_log.py`:scraper 四個 checker 的寫入改走這裡,**寫不進去
     也不拋例外**,改成把整筆紀錄印到 stdout。壞掉的若是錯誤處理器本身,
     絕不能連帶讓呼叫端的判斷結果消失——weekly 的新鮮度 gate 在全新 clone 上
     第一次執行就會踩到這條路徑。
   > processor/importer/calculator 的 `write_error_report()` 尚未改用
   > `common/error_log.py`,仍會在目錄情況下拋 `IsADirectoryError`;
   > 上面兩層防線已讓它不容易發生,但要根治得逐一改過去。

---

## 0. 備份清單(2026-08-01 校驗)

Mac 上 `/Users/poyilee/GitHubLL/my_stock_project/`:

| 路徑 | 內容 | 規模 | 校驗狀態 |
|---|---|---|---|
| `data/raw/` | 原始 CSV 鏡像 | 66,248 檔 / 24.96 G | 逐檔比對,Ubuntu 端 0 缺漏 |
| `data/backups/stock_db_20260801_115024.sql.gz` | PostgreSQL 全量 dump | 1.40 G | md5 `40a9e78a61a6b9c3a7482e58558bdb23`、`gzip -t` OK |
| `backup_ubuntu_20260801/models_selection/` | 選股模型 | 50 目錄 / 203 檔 | 檔數相符 |
| `backup_ubuntu_20260801/models_eps/` | EPS 模型 | 61 目錄 / 305 檔 | 檔數相符 |
| `backup_ubuntu_20260801/machine_local/` | 不入 git 的機器本地設定 | 2 檔 | 見 §6 |

### ⚠️ Mac 上有「同名但過期」的目錄,不要拿來還原

Mac 的 repo 根目錄底下另有一組舊資料,是 2026-05 的殘留,**佈局和內容都與現行不同**:

| 過期路徑 | 為什麼不能用 |
|---|---|
| `models_selection/`、`models_eps/` | 巢狀 `2026/04/` 佈局(現行是扁平 `2026-07-11/`);mtime 停在 2026-05-18,是 **ensemble 上線前的舊單 seed 模型** |
| `models_selection_old/`、`models_eps_old/` | 更早的版本 |
| `data/postgres/` | 只有 77 M(實際 DB 近 10 G),是殘缺的舊 data dir。**直接複製 live data dir 本來就不是有效備份**,一律用 §4 的 dump |
| `data/processed/` | 中間產物,由 `data/raw` + processor 重生,不需還原 |

**還原一律只認 `backup_ubuntu_20260801/` 這個目錄,以及 `data/raw/` 和 `data/backups/`。**

---

## 1. 系統前置

還原前環境(用同版本最省事):Ubuntu 24.04.4 LTS、Python 3.12.3、Docker 29.1.3、Docker Compose 2.40.3。

```bash
# Docker Engine + Compose plugin
sudo apt update
sudo apt install -y docker.io docker-compose-v2 python3-venv python3-pip rsync openssh-client git

# 免 sudo 跑 docker
sudo usermod -aG docker $USER
newgrp docker          # 或登出再登入

# 確認
docker --version && docker compose version && python3 --version
```

確認 Mac 連得到(後續每一步都靠它):

```bash
ssh poyilee@172.16.4.90 'echo OK'
```

不通的話先處理:Mac 要開「系統設定 → 一般 → 共享 → 遠端登入」,IP 也可能變動
(本文件寫的 `172.16.4.90` 是 2026-08-01 的值)。

---

## 2. Clone repo

```bash
mkdir -p ~/GitHubLL
git clone git@github.com:lordleeber/my_stock_project.git ~/GitHubLL/my_stock_project
cd ~/GitHubLL/my_stock_project
```

> **不要把 PAT 明文寫進 remote URL。** 舊機器的 `.git/config` 存的是
> `https://lordleeber:ghp_xxxx@github.com/...`,那顆 token 已建議輪替。改用 SSH
> key(上面的 `git@github.com:` 形式)或 credential helper。

啟用 repo 內的 git hooks(`core.hooksPath` 是 local 設定,每次 clone 都要重跑一次):

```bash
git config core.hooksPath .githooks
```

建出 5 個 error log 檔。它們被 `.gitignore` 的 `*.log` 忽略,全新 clone 不會有,
而 `docker-compose.yml` 會把它們 bind mount 進各 container:

```bash
touch error_processor.log error_importer.log error_calculator.log \
      error_valuation_calculator.log error_scraper.log
```

> **必須趕在第一次 `docker compose` 之前做。** bind mount 的 source 不存在時,
> docker 會照 target 自動建一個 **root 所有的目錄**,之後所有
> `open(..., "a")` 都固定拋 `IsADirectoryError`。壞掉的是錯誤處理器本身,
> 所以只在「真的出錯的那一天」才發作——而那天你正好最需要這份 log。
> 已經踩過一次,見 §狀態 的落差 4。

---

## 3. 還原 `data/raw`

```bash
./scripts/sync_raw_from_mac.sh --dry-run    # 先看要傳多少
./scripts/sync_raw_from_mac.sh              # 實際拉(24.96 G,視網速可能數小時)
```

腳本會自動排除 macOS 的 `.DS_Store` / `._*` / `.Spotlight-V100` 等雜訊。
可中斷重跑(`--partial` 續傳)。

驗證:

```bash
find data/raw -type f | wc -l     # 約 66,198(Mac 端 66,248,多出的 50 個是舊殘留)
du -sh data/raw                   # 約 25-26 G
```

> Mac 端比 Ubuntu 多 50 個檔,是因為同步腳本刻意不帶 `--delete`,舊機器上刪掉的
> 檔案在 Mac 留了下來。方向是「只多不少」,還原時無害。

---

## 4. 還原 PostgreSQL

### 4.1 起 DB container

`docker-compose.yml` 把 DB bind mount 到 `./data/postgres`。全新 clone 沒有這個
目錄,postgres 會自己 initdb 建一個空的。

```bash
docker compose up -d db
docker compose ps                 # 等 STATUS 出現 (healthy)
```

### 4.2 從 Mac 取回 dump 並匯入

```bash
mkdir -p data/backups
rsync -avh --progress \
  poyilee@172.16.4.90:/Users/poyilee/GitHubLL/my_stock_project/data/backups/stock_db_20260801_115024.sql.gz \
  data/backups/

# 先驗完整性再匯入
md5sum data/backups/stock_db_20260801_115024.sql.gz
# 應為 40a9e78a61a6b9c3a7482e58558bdb23
gzip -t data/backups/stock_db_20260801_115024.sql.gz && echo "gzip OK"

# 匯入(約 10-20 分鐘)
gunzip -c data/backups/stock_db_20260801_115024.sql.gz \
  | docker compose exec -T db psql -U user -d stock_db
```

dump 是用 `--no-owner --no-privileges` 產生的,匯進 `user` 這個 role 不會有權限問題。

### 4.3 驗證(對照 2026-08-01 的基準)

```bash
docker compose exec -T db psql -U user -d stock_db -c "
SELECT 'daily_quotes' t, count(*) rows, max(date) latest FROM daily_quotes
UNION ALL SELECT 'monthly_revenue', count(*), max(date) FROM monthly_revenue
UNION ALL SELECT 'technical_indicators', count(*), max(date) FROM technical_indicators
UNION ALL SELECT 'valuation_daily', count(*), max(date) FROM valuation_daily;"
```

備份當下的值:

| 表 | 列數 | 最新日期 |
|---|--:|---|
| `daily_quotes` | 2,872,581 | 2026-07-31 |
| `technical_indicators` | 2,872,581 | 2026-07-31 |
| `valuation_daily` | 1,949,448 | 2026-07-31 |
| `monthly_revenue` | 137,258 | 2026M06 |

public schema 共 **26** 張表:

```bash
docker compose exec -T db psql -U user -d stock_db -t -c \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

---

## 5. 還原模型目錄

```bash
DST=poyilee@172.16.4.90:/Users/poyilee/GitHubLL/my_stock_project/backup_ubuntu_20260801
rsync -avh --progress "$DST/models_selection" "$DST/models_eps" .
```

驗證:

```bash
echo "$(ls models_selection | wc -l) dirs, $(find models_selection -type f | wc -l) files"  # 50 dirs, 203 files
echo "$(ls models_eps        | wc -l) dirs, $(find models_eps        -type f | wc -l) files"  # 61 dirs, 305 files
```

`models_selection/<YYYY-MM-DD>/` 的 `<YYYY-MM-DD>` 是 train_through_playbook_date;
最新一版是 `2026-07-11`。少了這些目錄的話 backtest 的 walk-forward 選模會失敗,
而且要重建得先有 DB(§4)才能重跑。

---

## 6. 還原機器本地設定(不在 git 裡)

```bash
rsync -avh poyilee@172.16.4.90:/Users/poyilee/GitHubLL/my_stock_project/backup_ubuntu_20260801/machine_local/ /tmp/machine_local/
```

| 檔案 | 放回哪裡 | 說明 |
|---|---|---|
| `stock-notify.env` | `~/.config/systemd/user/stock-notify.env` | **含真實 ntfy topic**。手機訂閱的就是這個 topic,弄丟就收不到失敗推播,得重設 topic 並重新訂閱 |
| `settings.local.json` | `.claude/settings.local.json` | Claude Code 的本機權限設定,可有可無 |

```bash
mkdir -p ~/.config/systemd/user
cp /tmp/machine_local/stock-notify.env ~/.config/systemd/user/
chmod 600 ~/.config/systemd/user/stock-notify.env      # 權限務必 600

cp /tmp/machine_local/settings.local.json .claude/
```

---

## 7. 重建 venv

```bash
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements-host.lock.txt
```

`requirements-host.lock.txt` 是 2026-08-01 從舊機器 `pip freeze` 出來的完整清單
(21 個套件,含 pandas 3.0.3 / numpy 2.4.6 / lightgbm 4.6.0 / scikit-learn 1.8.0)。

> `requirements-host.txt` 只列「額外加裝」的套件,不足以重建 venv,還原請用 `.lock.txt`。

驗證:

```bash
venv/bin/python3 -c "import pandas, numpy, lightgbm, sklearn, sqlalchemy; print('imports OK')"
venv/bin/python3 -c "from common.db import get_db_url; import sqlalchemy as sa; \
  print(sa.create_engine(get_db_url()).connect().execute(sa.text('select count(*) from daily_quotes')).scalar())"
# 應印出 2872581
```

---

## 8. 建 Docker images

`processor` / `importer` / `calculator` **不掛 source code volume**,程式是烤進 image 的:

```bash
docker compose build scraper-daily processor importer calculator
```

---

## 9. 裝回 systemd 排程

完整說明見 [`schedules_ubuntu/CLAUDE.md`](schedules_ubuntu/CLAUDE.md)。摘要:

```bash
mkdir -p ~/.config/systemd/user
cp schedules_ubuntu/*.service schedules_ubuntu/*.timer ~/.config/systemd/user/

systemctl --user daemon-reload
for t in stock-daily-update stock-daily-retry stock-weekly-update \
         stock-monthly-update stock-xbrl-scrape-daily stock-playbook-run; do
  systemctl --user enable --now ${t}.timer
done

# 沒開 linger 的話登出就不會觸發
sudo loginctl enable-linger "$USER"
```

前提:專案要放在 `~/GitHubLL/my_stock_project`(unit 裡寫死 `WorkingDirectory=%h/GitHubLL/my_stock_project`)。
放別處就得改 `*.service` 裡的 `WorkingDirectory` 和 `ExecStart`。

驗證(應列出 6 個 stock-* timer):

```bash
systemctl --user list-timers --all | grep stock
```

> 舊機器上部署中的 unit 與 repo 版本**逐檔相同**,沒有手改過的內容需要另外還原。

---

## 10. 端到端驗收

```bash
# 1. 先留一份還原前的名單當對照組
cp models_selection/2026-07-11/candidates_scored.csv /tmp/candidates_before.csv

# 2. 用最新的 playbook date 重跑評分
venv/bin/python3 strategies/step5_score_and_publish.py --date 2026-07-11

# 3. 應與對照組完全相同(同 DB + 同 model + 同 code = 同結果)
diff /tmp/candidates_before.csv models_selection/2026-07-11/candidates_scored.csv \
  && echo "✓ 名單逐行相同,還原成功"

# 4. 跑一天的 daily pipeline(挑已經有資料的交易日,等於重跑覆寫)
./schedules/daily_update.sh 20260731
```

第 3 步是最強的驗收:名單一致代表 DB、模型、程式碼三者都還原到位。
`candidates_scored.csv` 是外部 my_trade_project 監控看板讀的檔案(top-25)。

> 若 diff 有差異,先查 DB 列數(§4.3)和模型檔數(§5)對不對,再查 venv 套件版本
> 是否與 `requirements-host.lock.txt` 一致 —— LightGBM 版本不同會讓預測值有微小浮動。

---

## 附錄:還原順序為何是這樣

```
系統前置 → clone → data/raw → DB dump → models → 本地設定 → venv → images → systemd
                      └─────────┬────────┘
                      這兩個彼此獨立,可並行拉(都很慢)
```

- `data/processed` **不用還原**:由 `data/raw` + processor 重生。
- DB **不能**用複製 `data/postgres` 的方式還原:那是 live data dir,複製時可能
  拿到寫到一半的 page 或還沒 flush 的 WAL。一律走 `pg_dump`。
- models 理論上可由 DB 重跑重生(`scripts/batch_train_eps_full.sh` 全跑約 28 分鐘,
  selection model 另計),但前提是 DB 先還原完成 —— 直接還原檔案快得多。

## 附錄:之後的例行備份

```bash
./scripts/backup_db.sh              # dump + 推到 Mac
./scripts/sync_raw_to_mac.sh        # data/raw 推到 Mac
./scripts/sync_raw_to_nas.sh        # data/raw 推到 NAS
```

`backup_db.sh` 每跑一次會在 `data/backups/` 留一個帶時間戳的檔案,不會自動清理,
偶爾要自己刪舊的。models 目錄目前**沒有**自動備份腳本,是手動 rsync 的。
