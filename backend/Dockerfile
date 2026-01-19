FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 啟動 FastAPI，host 設為 0.0.0.0 才能被容器外部存取
# --reload 讓您修改程式碼後自動重啟 server (開發模式)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
