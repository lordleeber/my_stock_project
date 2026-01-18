# 使用輕量的 Python 映像檔
FROM python:3.10-slim

# 設定工作目錄
WORKDIR /app

# 安裝必要套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 建立非 root 使用者
RUN useradd -m appuser

# 複製程式碼與資料
COPY . .

# 建立資料存放目錄並設定權限
RUN mkdir -p /app/data && chown -R appuser:appuser /app

# 切換到非 root 使用者
USER appuser

# 環境變數預設值
ENV OUTPUT_DIR=/app/data
ENV FETCH_DELAY=3.0
ENV MARKET_TYPE=ALL

# 執行腳本
CMD ["python", "main.py"]
