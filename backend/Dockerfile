FROM python:3.10-slim

WORKDIR /app

# 相對路徑: backend/requirements.txt (需從根目錄 build)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製 Strategy 模組
COPY strategy /app/strategy

# 複製 Scanner 模組
COPY scanner /app/scanner

# 複製 Backend 程式碼
COPY backend/ .

# 設定 PYTHONPATH
ENV PYTHONPATH="${PYTHONPATH}:/app"

# 啟動 FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]