FROM python:3.10-slim

# 安裝 Polars (資料處理) 和 PyArrow (Parquet 支援)
RUN pip install polars pyarrow

WORKDIR /app
COPY . .

# 預設執行轉換腳本
CMD ["python", "convert.py"]
