#!/usr/bin/env bash
# backup_db.sh — pg_dump stock_db 並推送到 Mac（可重跑）
#
# 用法：
#   ./scripts/backup_db.sh              # dump + 推送到 Mac
#   ./scripts/backup_db.sh --dry-run    # 只 dump 到本機，不推送
#   ./scripts/backup_db.sh --local-only # 同 --dry-run（語意較清楚的別名）
#
# 注意：
#   - DB 是 bind mount 到 ./data/postgres。直接複製 live data dir 不是安全備份
#     （torn page / 未 flush 的 WAL），一律走 pg_dump。
#   - dump 在 container 內執行，避免 host 端 pg_dump 版本與 server 不匹配。
#   - dump 檔留在 data/backups/（已被 .gitignore 的 data/ 蓋掉），不會進 repo，
#     也不在 sync_raw_to_mac.sh 的同步路徑（那支只同步 data/raw/）內。
#   - 還原：gunzip -c <dump>.sql.gz | docker compose exec -T db psql -U user -d stock_db
set -euo pipefail

cd "$(dirname "$0")/.."

DB_SERVICE="db"
DB_USER="user"
DB_NAME="stock_db"

LOCAL_DIR="data/backups"

DST_USER="poyilee"
DST_HOST="172.16.4.90"
DST_PATH="/Users/poyilee/Documents/GitHubLL/my_stock_project/data/backups/"

PUSH=1
case "${1:-}" in
  "")                     ;;
  --dry-run|--local-only) PUSH=0; echo "[local-only] 只 dump 到本機，不推送到 Mac" ;;
  *)                      echo "未知參數：$1（只接受 --dry-run / --local-only）" >&2; exit 1 ;;
esac

if ! docker compose ps --status running --services | grep -qx "${DB_SERVICE}"; then
  echo "db container 未執行，請先 docker compose up -d ${DB_SERVICE}" >&2
  exit 1
fi

mkdir -p "${LOCAL_DIR}"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="${LOCAL_DIR}/${DB_NAME}_${STAMP}.sql.gz"

echo "[dump] ${DB_NAME} -> ${OUT}"
# 失敗時不要留下半截的 .sql.gz 讓人誤以為備份成功。
# pipefail 已開，pg_dump 失敗會讓整條 pipeline 失敗。
if ! docker compose exec -T "${DB_SERVICE}" \
        pg_dump -U "${DB_USER}" -d "${DB_NAME}" --no-owner --no-privileges \
        | gzip -c > "${OUT}"; then
  rm -f "${OUT}"
  echo "pg_dump 失敗，已移除不完整的 ${OUT}" >&2
  exit 1
fi

echo "[dump] 完成：$(du -h "${OUT}" | cut -f1)"

if [[ "${PUSH}" -eq 0 ]]; then
  echo "[skip] 未推送（--local-only）"
  exit 0
fi

echo "[push] -> ${DST_USER}@${DST_HOST}:${DST_PATH}"
ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=4 \
  "${DST_USER}@${DST_HOST}" "mkdir -p '${DST_PATH}'"

rsync -avh \
  --progress --partial \
  -e "ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=4" \
  "${OUT}" \
  "${DST_USER}@${DST_HOST}:${DST_PATH}"

echo "[done] ${OUT}"
