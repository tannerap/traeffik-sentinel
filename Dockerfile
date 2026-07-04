FROM python:3-alpine

# Portainer may still start this container as user "watchdog" from older stacks.
# UID 0 keeps socket access working like Traefik (root), without extra compose config.
RUN apk add --no-cache curl \
    && echo 'watchdog:x:0:0:watchdog:/:/sbin/nologin' >> /etc/passwd \
    && echo 'watchdog:x:0:0:watchdog:/:/sbin/nologin' >> /etc/passwd

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY watchdog/watchdog.py watchdog/discovery.py ./

CMD ["python", "-u", "/app/watchdog.py"]
