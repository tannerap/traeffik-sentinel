FROM python:3-alpine

RUN apk add --no-cache curl

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watchdog/watchdog.py watchdog/discovery.py ./

CMD ["python", "-u", "/app/watchdog.py"]
