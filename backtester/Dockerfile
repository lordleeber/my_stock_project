FROM python:3.10-slim

WORKDIR /app

# 安裝相依套件
COPY backtester/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 Strategy 模組
COPY strategy /app/strategy

# 複製 Backtester 程式碼
COPY backtester/ .

# 設定 PYTHONPATH
ENV PYTHONPATH="${PYTHONPATH}:/app"

CMD ["python", "main.py"]