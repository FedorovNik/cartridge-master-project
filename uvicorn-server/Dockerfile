FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8080 \
    DB_NAME=/data/inventory.db

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./backend/frontend

WORKDIR /app/backend
RUN mkdir -p /data

EXPOSE 8080

CMD ["python", "server.py"]