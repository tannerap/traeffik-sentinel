FROM python:3-alpine

RUN apk add --no-cache curl \
    && addgroup -S watchdog \
    && adduser -S watchdog -G watchdog

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watchdog/watchdog.py ./watchdog.py
COPY config/targets.json.example ./config/targets.json

USER watchdog

ENV CONFIG_PATH=/app/config/targets.json \
    CHECK_INTERVAL=300 \
    RETRY_WAIT=60 \
    CURL_TIMEOUT=15 \
    TRAEFIK_CONTAINER=traefik

CMD ["python", "-u", "/app/watchdog.py"]
