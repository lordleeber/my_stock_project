FROM python:3.10-slim

WORKDIR /app

# 安裝相依套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 預設執行轉換腳本
CMD ["python", "convert_daily.py"]
