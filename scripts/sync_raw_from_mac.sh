#!/usr/bin/env bash
# sync_raw_from_mac.sh — 從 Mac 同步 data/raw 到本機（可重跑、可續傳）
#
# 用法：
#   ./scripts/sync_raw_from_mac.sh              # 實際同步
#   ./scripts/sync_raw_from_mac.sh --dry-run    # 預演（不實際傳輸）
set -euo pipefail

SRC_USER="poyilee"
SRC_HOST="172.16.4.17"
SRC_PATH="/Users/poyilee/Documents/GitHubLL/my_stock_project/data/raw/"

DST_PATH="/home/poyi/GitHubLL/my_stock_project/data/raw/"

DRY_RUN=""
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN="--dry-run"
  echo "[dry-run] 只預演，不實際傳輸"
fi

mkdir -p "${DST_PATH}"

rsync -avh \
  ${DRY_RUN} \
  --progress --partial \
  --human-readable \
  --exclude='.DS_Store' \
  --exclude='._*' \
  --exclude='.Spotlight-V100' \
  --exclude='.Trashes' \
  --exclude='.fseventsd' \
  -e "ssh -o ServerAliveInterval=30 -o ServerAliveCountMax=4" \
  "${SRC_USER}@${SRC_HOST}:${SRC_PATH}" \
  "${DST_PATH}"
