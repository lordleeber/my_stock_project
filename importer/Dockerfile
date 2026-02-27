FROM python:3.10-slim

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=60

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "import_daily.py"]
