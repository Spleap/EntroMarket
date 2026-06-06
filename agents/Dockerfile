FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY .env.example README.md ./
COPY web/dist ./web/dist

RUN mkdir -p /app/logs /app/state /app/shared /app/web

EXPOSE 8765

CMD ["python", "console_server.py", "--host", "0.0.0.0", "--port", "8765"]
