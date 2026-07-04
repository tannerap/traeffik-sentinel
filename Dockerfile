FROM python:3-alpine

RUN apk add --no-cache curl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watchdog/watchdog.py watchdog/discovery.py ./

ENV CHECK_INTERVAL=300 \
    RETRY_WAIT=60 \
    CURL_TIMEOUT=15 \
    TRAEFIK_CONTAINER=traefik \
    WATCHDOG_CONTAINER=traeffik-sentinel \
    DEFAULT_SCHEME=https

CMD ["python", "-u", "/app/watchdog.py"]
