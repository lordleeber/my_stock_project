#!/usr/bin/env bash
# sync_raw_to_nas.sh — 從本機推送 data/raw 到 Ubuntu NAS server（可重跑、可續傳）
#
# 用法：
#   ./scripts/sync_raw_to_nas.sh              # 實際同步
#   ./scripts/sync_raw_to_nas.sh --dry-run    # 預演（不實際傳輸）
#
# 注意：
#   - 結尾斜線代表「把 raw 的內容同步進目標的 raw」，勿移除。
#   - 預設不帶 --delete；目標端多出來的檔不會被刪。若要嚴格鏡像再自行加。
set -euo pipefail

SRC_PATH="/home/poyi/GitHubLL/my_stock_project/data/raw/"

DST_USER="poyi"
DST_HOST="100.68.32.34"
DST_PATH="/nas/data/raw/"

DRY_RUN=""
case "${1:-}" in
  "")          ;;
  --dry-run)   DRY_RUN="--dry-run"; echo "[dry-run] 只預演，不實際傳輸" ;;
  *)           echo "未知參數：$1（只接受 --dry-run）" >&2; exit 1 ;;
esac

if [[ ! -d "${SRC_PATH}" ]]; then
  echo "來源目錄不存在：${SRC_PATH}" >&2
  exit 1
fi

ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=4 \
  "${DST_USER}@${DST_HOST}" "mkdir -p '${DST_PATH}'"

rsync -avh \
  ${DRY_RUN} \
  --progress --partial \
  --human-readable \
  -e "ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=4" \
  "${SRC_PATH}" \
  "${DST_USER}@${DST_HOST}:${DST_PATH}"
