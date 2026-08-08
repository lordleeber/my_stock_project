#!/bin/bash

# 在跑任何 docker compose 之前，先確保 5 個 error log 檔存在。
#
# 這些檔案被 .gitignore 的 *.log 忽略，所以全新 clone 上不存在；而
# docker-compose.yml 用 **file** bind mount 把它們掛進 container，bind mount 的
# source 不存在時 docker 會照 target 自動建一個 root 所有的**目錄**，之後所有
# open(..., "a") 都固定拋 IsADirectoryError。
#
# 壞掉的是錯誤處理器本身，所以只在「真的出錯的那一天」才發作——那天你正好最需要
# 這份 log。2026-08-01 已經踩過一次（RESTORE.md §落差4，三個檔案全變成目錄，
# 直到 8/8 查資料完整性時才從 traceback 發現）。
#
# RESTORE.md §2 有同樣的 touch 步驟，但那是「人記得照做」才有效；這支是給排程用
# 的自動保險。已經變成目錄的情況需要人工介入（rmdir 要 root），這裡只負責明確
# 報出來，不試圖自己修。

set -euo pipefail

cd "$(dirname "$0")/.."

ERROR_LOGS=(
    error_scraper.log
    error_processor.log
    error_importer.log
    error_calculator.log
    error_valuation_calculator.log
)

broken=0
for f in "${ERROR_LOGS[@]}"; do
    if [ -d "$f" ]; then
        echo "✗ $f 是目錄，不是檔案。docker 在 bind mount source 不存在時會這樣建。" >&2
        echo "  修法：確認沒有 container 在跑，然後 sudo rmdir '$PWD/$f' && touch '$f'" >&2
        broken=1
    elif [ ! -e "$f" ]; then
        touch "$f"
        echo "✓ created $f"
    fi
done

exit "$broken"
