#!/usr/bin/env bash
# create_readonly_user.sh — 在 stock_db 建立/更新一個只能 SELECT 的 role（可重跑）
#
# 用法：
#   ./scripts/create_readonly_user.sh                       # role=readonly, 密碼=readonly
#   RO_USER=grafana RO_PASSWORD='xxx' ./scripts/create_readonly_user.sh
#   ./scripts/create_readonly_user.sh --show                # 只印出目前授權狀態
#
# 行為：
#   - role 不存在就 CREATE，已存在就 ALTER（重設密碼、確保 NOSUPERUSER/NOCREATEDB/
#     NOCREATEROLE/NOINHERIT 之外的旗標乾淨）。整支可重複執行。
#   - 授 CONNECT / USAGE on public / SELECT on 既有 tables+views+sequences。
#   - 另外設 ALTER DEFAULT PRIVILEGES FOR ROLE user：pipeline 之後新建的表
#     （calculator/importer 會 drop+create）自動帶上 SELECT，不用每次重跑這支。
#     這條只對「由 user 建立」的物件生效——本專案所有表都是 user 建的。
#
# 注意：
#   - PG15 的 public schema 預設已從 PUBLIC 收回 CREATE，所以新 role 不需要額外
#     REVOKE 就無法建表。
#   - 想連「未來有人誤 GRANT 寫權限」都一併封死，可加：
#       ALTER ROLE <role> SET default_transaction_read_only = on;
#     代價是該 role 連 temp table 都建不了（部分 BI/報表工具會壞），故預設不開。
#   - pg_hba 對非 localhost 連線是 scram-sha-256，密碼是必要的；container 內走
#     unix socket（trust），所以這支不需要 superuser 密碼。
set -euo pipefail

cd "$(dirname "$0")/.."

DB_SERVICE="db"
DB_SUPERUSER="user"   # 物件 owner，ALTER DEFAULT PRIVILEGES 要綁在它身上
DB_NAME="stock_db"

RO_USER="${RO_USER:-readonly}"
RO_PASSWORD="${RO_PASSWORD:-readonly}"

SHOW_ONLY=0
case "${1:-}" in
  "")     ;;
  --show) SHOW_ONLY=1 ;;
  *)      echo "未知參數：$1（只接受 --show）" >&2; exit 1 ;;
esac

if ! docker compose ps --status running --services | grep -qx "${DB_SERVICE}"; then
  echo "db container 未執行，請先 docker compose up -d ${DB_SERVICE}" >&2
  exit 1
fi

psql_super() {
  docker compose exec -T "${DB_SERVICE}" psql -U "${DB_SUPERUSER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 "$@"
}

show_state() {
  echo "[state] role 旗標："
  psql_super -c "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
                   FROM pg_roles WHERE rolname = '${RO_USER}';"
  echo "[state] public schema 內拿到 SELECT 的表數量 / 總表數："
  psql_super -tAc "SELECT count(*) FILTER (WHERE has_table_privilege('${RO_USER}', c.oid, 'SELECT')),
                          count(*)
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p');"
  echo "[state] 是否誤帶寫權限（列出任何 INSERT/UPDATE/DELETE/TRUNCATE 的表）："
  psql_super -tAc "SELECT string_agg(c.relname, ', ')
                     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p')
                      AND (has_table_privilege('${RO_USER}', c.oid, 'INSERT')
                        OR has_table_privilege('${RO_USER}', c.oid, 'UPDATE')
                        OR has_table_privilege('${RO_USER}', c.oid, 'DELETE')
                        OR has_table_privilege('${RO_USER}', c.oid, 'TRUNCATE'));"
}

if [[ "${SHOW_ONLY}" -eq 1 ]]; then
  if [[ -z "$(psql_super -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${RO_USER}';")" ]]; then
    echo "role ${RO_USER} 不存在。" >&2
    exit 1
  fi
  show_state
  exit 0
fi

# 密碼走 psql 變數 :'ro_pw'（會被正確 quote），不要直接內插進 SQL 字串。
# 注意：psql -c 不做變數展開，必須從 stdin 餵 SQL。
if [[ -z "$(psql_super -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${RO_USER}';")" ]]; then
  echo "[create] role ${RO_USER}"
  VERB="CREATE"
else
  echo "[update] role ${RO_USER} 已存在，重設密碼與旗標"
  VERB="ALTER"
fi
psql_super -v ro_pw="${RO_PASSWORD}" -f - <<SQL
${VERB} ROLE "${RO_USER}"
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  PASSWORD :'ro_pw';
SQL

echo "[grant] CONNECT / USAGE / SELECT"
psql_super \
  -c "GRANT CONNECT ON DATABASE \"${DB_NAME}\" TO \"${RO_USER}\";" \
  -c "GRANT USAGE ON SCHEMA public TO \"${RO_USER}\";" \
  -c "GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"${RO_USER}\";" \
  -c "GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO \"${RO_USER}\";"

echo "[grant] default privileges（之後由 ${DB_SUPERUSER} 新建的表自動帶 SELECT）"
psql_super \
  -c "ALTER DEFAULT PRIVILEGES FOR ROLE \"${DB_SUPERUSER}\" IN SCHEMA public GRANT SELECT ON TABLES TO \"${RO_USER}\";" \
  -c "ALTER DEFAULT PRIVILEGES FOR ROLE \"${DB_SUPERUSER}\" IN SCHEMA public GRANT SELECT ON SEQUENCES TO \"${RO_USER}\";"

show_state

echo "[done] 連線字串："
echo "  postgresql://${RO_USER}:<password>@localhost:5419/${DB_NAME}"
