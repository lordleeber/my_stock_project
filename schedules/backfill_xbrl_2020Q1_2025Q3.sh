#!/bin/bash

set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/backfill_xbrl_2020Q1_2025Q3_$(date +%Y%m%d_%H%M%S).log"

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Backfill Started" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Range: 2020Q1 ~ 2025Q3" | tee -a "$LOG_FILE"
echo "FORCE_REPROCESS: ${FORCE_REPROCESS:-0}" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"

for year in 2020 2021 2022 2023 2024 2025; do
    for quarter in 1 2 3 4; do
        if [ "$year" -eq 2025 ] && [ "$quarter" -gt 3 ]; then
            break
        fi

        target="${year}Q${quarter}"
        echo "" | tee -a "$LOG_FILE"
        echo "[RUN] $target" | tee -a "$LOG_FILE"

        if docker compose run --rm \
            -e FORCE_REPROCESS=${FORCE_REPROCESS:-0} \
            scraper-quarterly \
            python3 scraper/quarterly/fetch_xbrl.py --year "$year" --quarter "$quarter" 2>&1 | tee -a "$LOG_FILE"; then
            echo "[OK] $target" | tee -a "$LOG_FILE"
        else
            echo "[FAIL] $target" | tee -a "$LOG_FILE"
            exit 1
        fi
    done
done

echo "========================================" | tee -a "$LOG_FILE"
echo "XBRL Backfill Completed" | tee -a "$LOG_FILE"
echo "Date: $(date)" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
