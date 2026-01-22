#!/bin/bash

# 取得腳本所在目錄的上一層 (專案根目錄)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# 優先使用參數傳入的日期，若無則使用今天日期 YYYYMMDD
TODAY=${1:-$(date +"%Y%m%d")}

echo "========================================"
echo "Starting Daily Stock Update: $TODAY"
echo "Project Dir: $PROJECT_DIR"
echo "========================================"

# [重要] 強制重新建置容器，確保最新的代碼生效
echo "Rebuilding containers..."
docker-compose build scraper processor importer calculator

# 1. Scraper
echo "[1/4] Running Scraper for $TODAY..."
docker-compose run --rm -e START_DATE=$TODAY -e END_DATE=$TODAY scraper
if [ $? -ne 0 ]; then echo "Scraper failed"; exit 1; fi

# 2. Processor
echo "[2/4] Running Processor for $TODAY..."
docker-compose run --rm -e START_DATE=$TODAY -e END_DATE=$TODAY processor
if [ $? -ne 0 ]; then echo "Processor failed"; exit 1; fi

# 3. Importer
echo "[3/4] Running Importer for $TODAY..."
docker-compose run --rm -e START_DATE=$TODAY -e END_DATE=$TODAY importer
if [ $? -ne 0 ]; then echo "Importer failed"; exit 1; fi

# 4. Calculator
echo "[4/4] Running Calculator..."
docker-compose run --rm calculator
if [ $? -ne 0 ]; then echo "Calculator failed"; exit 1; fi

echo "========================================"
echo "Daily Update for $TODAY Completed Successfully!"
echo "========================================"
