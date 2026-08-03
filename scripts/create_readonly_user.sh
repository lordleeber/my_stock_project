#!/usr/bin/env bash
# create_readonly_user.sh — 在 stock_db 建立/維護一個只能 SELECT 的 role（可重跑）
#
# 用法：
#   RO_PASSWORD='...' ./scripts/create_readonly_user.sh                   # 首次建立（密碼必填）
#   ./scripts/create_readonly_user.sh                                     # role 已存在：只補授權，不動密碼
#   RO_USER=grafana RO_PASSWORD='...' ./scripts/create_readonly_user.sh    # 另開一個
#   RO_PASSWORD='...' ./scripts/create_readonly_user.sh --reset-password   # 明確換密碼
#   ./scripts/create_readonly_user.sh --show                              # 只印出目前授權狀態
#
# 行為：
#   - role 不存在就 CREATE（此時 RO_PASSWORD 必填），已存在就重申旗標並補授權。
#     整支可重複執行。
#   - 密碼只在「建立」或「明確 --reset-password」時才會被寫入。已存在的 role 帶著
#     RO_PASSWORD 但沒有 --reset-password 會直接報錯，不會靜默覆蓋線上密碼——
#     這支的常用情境是「重跑一次確認授權還在」，那條路徑絕不能動到憑證。
#   - 授 CONNECT / USAGE on public / SELECT on 既有 tables+views+matviews。
#   - 另外設 ALTER DEFAULT PRIVILEGES FOR ROLE user：pipeline 之後新建的表
#     （calculator/importer 會 drop+create）自動帶上 SELECT，不用每次重跑這支。
#     這條只對「由 user 建立」的物件生效——本專案所有表都是 user 建的。
#   - 整批 DDL 走單一 transaction（--single-transaction）。中途失敗會整批 rollback，
#     不會留下「能登入但零權限」的半套 role。
#
# 設計取捨：
#   - PG14+ 有內建的 pg_read_all_data，`GRANT pg_read_all_data TO <role>` 一行就能
#     取代下面所有 GRANT/ALTER DEFAULT PRIVILEGES（已實測等價）。這裡刻意不用：
#     它是 cluster 層級的 role membership，會一併涵蓋將來新增的 schema 以及同一個
#     cluster 內其他資料庫。本專案要的是「只有 stock_db 的 public」這個窄範圍。
#     若哪天真的想放寬到整個 cluster，換成那一行、並刪掉 default privileges 即可。
#   - 沒有授 SELECT ON SEQUENCES：public 目前沒有任何 sequence，而純讀取的 role
#     即使表上有 SERIAL 也不需要碰 sequence。真的加了 sequence 又要讀，再補。
#   - 沒有開 default_transaction_read_only：它能連「未來有人誤 GRANT 寫權限」都
#     一併封死，但代價是該 role 連 temp table 都建不了（部分 BI/報表工具會壞），
#     故預設不開。要開就加：
#       ALTER ROLE <role> SET default_transaction_read_only = on;
#
# 注意：
#   - PG15 的 public schema 預設已從 PUBLIC 收回 CREATE，所以新 role 不需要額外
#     REVOKE 就無法建表。
#   - pg_hba 對非 localhost 連線是 scram-sha-256，密碼是必要的；container 內走
#     unix socket（trust），所以這支不需要 superuser 密碼。
set -euo pipefail

cd "$(dirname "$0")/.."

DB_SERVICE="db"
DB_SUPERUSER="user"   # 物件 owner，ALTER DEFAULT PRIVILEGES 要綁在它身上
DB_NAME="stock_db"

RO_USER="${RO_USER:-readonly}"

SHOW_ONLY=0
RESET_PASSWORD=0
case "${1:-}" in
  "")               ;;
  --show)           SHOW_ONLY=1 ;;
  --reset-password) RESET_PASSWORD=1 ;;
  *)                echo "未知參數：$1（只接受 --show / --reset-password）" >&2; exit 1 ;;
esac

# RO_USER 會被內插進 SQL identifier 與字串常值，而連線身分是 superuser。
# 沒有這道檢查，一個含引號的 role 名就是一發以 superuser 執行的 SQL injection。
if [[ ! "${RO_USER}" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
  echo "RO_USER 不合法：'${RO_USER}'" >&2
  echo "只接受 ^[a-z_][a-z0-9_]{0,62}\$（小寫、數字、底線；不需要引號跳脫的形式）。" >&2
  exit 1
fi

if ! docker compose ps --status running --services | grep -qx "${DB_SERVICE}"; then
  echo "db container 未執行，請先 docker compose up -d ${DB_SERVICE}" >&2
  exit 1
fi

psql_super() {
  docker compose exec -T "${DB_SERVICE}" psql -U "${DB_SUPERUSER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 "$@"
}

# 「查不到」與「查詢失敗」必須分開：psql 掛掉時 -tAc 也回空字串，
# 當成「role 不存在」會讓後面走錯分支。
role_exists() {
  local out
  if ! out="$(psql_super -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${RO_USER}';")"; then
    echo "查詢 pg_roles 失敗（psql 未正常結束），中止。" >&2
    exit 1
  fi
  [[ -n "${out}" ]]
}

show_state() {
  echo "[state] role 旗標："
  psql_super -c "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                        rolreplication, rolbypassrls
                   FROM pg_roles WHERE rolname = '${RO_USER}';"
  echo "[state] public schema 內拿到 SELECT 的表數量 / 總表數："
  psql_super -tAc "SELECT count(*) FILTER (WHERE has_table_privilege('${RO_USER}', c.oid, 'SELECT')),
                          count(*)
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p');"
  echo "[state] 是否誤帶寫權限（列出任何 INSERT/UPDATE/DELETE/TRUNCATE 的表）："
  psql_super -tAc "SELECT coalesce(string_agg(c.relname, ', '), '(無)')
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p')
                      AND (has_table_privilege('${RO_USER}', c.oid, 'INSERT')
                        OR has_table_privilege('${RO_USER}', c.oid, 'UPDATE')
                        OR has_table_privilege('${RO_USER}', c.oid, 'DELETE')
                        OR has_table_privilege('${RO_USER}', c.oid, 'TRUNCATE'));"
}

if [[ "${SHOW_ONLY}" -eq 1 ]]; then
  if ! role_exists; then
    echo "role ${RO_USER} 不存在。" >&2
    exit 1
  fi
  show_state
  exit 0
fi

# 決定要不要寫密碼。三條路：建立（必填）、明確 reset（必填）、其他（一律不動）。
if role_exists; then
  if [[ "${RESET_PASSWORD}" -eq 1 ]]; then
    if [[ -z "${RO_PASSWORD:-}" ]]; then
      echo "--reset-password 需要 RO_PASSWORD。" >&2
      exit 1
    fi
    echo "[update] role ${RO_USER} 已存在，重設密碼並重申旗標"
    ROLE_SQL="ALTER ROLE \"${RO_USER}\" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'ro_pw';"
  elif [[ -n "${RO_PASSWORD:-}" ]]; then
    echo "role ${RO_USER} 已存在，但收到了 RO_PASSWORD。" >&2
    echo "  要換密碼：加上 --reset-password" >&2
    echo "  只想補授權：不要帶 RO_PASSWORD 再跑一次" >&2
    exit 1
  else
    echo "[update] role ${RO_USER} 已存在，重申旗標並補授權（不動密碼）"
    ROLE_SQL="ALTER ROLE \"${RO_USER}\" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;"
  fi
else
  if [[ -z "${RO_PASSWORD:-}" ]]; then
    echo "role ${RO_USER} 不存在，建立時必須提供 RO_PASSWORD。" >&2
    echo "  RO_PASSWORD='...' $0" >&2
    exit 1
  fi
  echo "[create] role ${RO_USER}"
  ROLE_SQL="CREATE ROLE \"${RO_USER}\" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'ro_pw';"
fi

# 密碼走 psql 變數 :'ro_pw'（會被正確 quote），不要直接內插進 SQL 字串。
# 注意：psql -c 不做變數展開，也不吃 --single-transaction，所以 SQL 從 stdin 餵。
echo "[apply] role 旗標 + CONNECT / USAGE / SELECT + default privileges（單一 transaction）"
psql_super --single-transaction -v ro_pw="${RO_PASSWORD:-}" -f - <<SQL
${ROLE_SQL}
GRANT CONNECT ON DATABASE "${DB_NAME}" TO "${RO_USER}";
GRANT USAGE ON SCHEMA public TO "${RO_USER}";
GRANT SELECT ON ALL TABLES IN SCHEMA public TO "${RO_USER}";
ALTER DEFAULT PRIVILEGES FOR ROLE "${DB_SUPERUSER}" IN SCHEMA public
  GRANT SELECT ON TABLES TO "${RO_USER}";
SQL

show_state

# port 從 compose 問，不要寫死——docker-compose.yml 才是那個數字的來源。
HOST_PORT="$(docker compose port "${DB_SERVICE}" 5432 2>/dev/null || true)"
echo "[done] 連線字串："
echo "  postgresql://${RO_USER}:<password>@${HOST_PORT:-localhost:5419}/${DB_NAME}"
