FROM python:3.10-slim

WORKDIR /app

# 系統相依套件
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝相依套件 (路徑相對於根目錄)
COPY scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 建立非 root 使用者
RUN useradd -m appuser

# 複製 Common 模組
COPY common /app/common

# 複製 Scraper 程式碼（保留 /app/scraper 套件結構）
COPY scraper /app/scraper

# 建立資料存放目錄並設定權限
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# 設定 PYTHONPATH 以便能匯入 common
ENV PYTHONPATH="${PYTHONPATH}:/app"

USER appuser

# 環境變數預設值
ENV OUTPUT_DIR=/app/data
ENV FETCH_DELAY=3.0
ENV MARKET_TYPE=ALL

# 執行腳本
CMD ["python", "scraper/scraper_daily.py"]
