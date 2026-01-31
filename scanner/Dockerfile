FROM python:3.10-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 套件
RUN pip install --no-cache-dir \
    psycopg2-binary \
    pandas \
    sqlalchemy \
    matplotlib \
    mplfinance

# 複製掃描器
COPY volume_spike_scanner.py /app/
COPY plot_candlestick.py /app/

CMD ["python", "volume_spike_scanner.py"]
