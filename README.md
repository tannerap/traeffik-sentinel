# traeffik-sentinel

Docker-Watchdog-Container zur Überwachung öffentlicher Web-Dienste hinter Traefik. Ziele werden automatisch aus **Traefik Docker-Labels** erkannt.

## Schnellstart

```bash
docker compose up -d --build
```

## Funktionsweise

1. Liest Traefik-Labels von laufenden Containern via Docker Socket
2. Prüft die öffentlichen URLs per curl
3. Bei Fehler: Container-Restart, nach 60s erneut prüfen, dann Traefik-Restart

## Beispiel-Labels

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.myapp.rule=Host(`app.example.com`)
  - traefik.http.routers.myapp.entrypoints=websecure
  - traefik.http.routers.myapp.tls=true
```

## Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `CHECK_INTERVAL` | `300` | Sekunden zwischen Prüfzyklen |
| `RETRY_WAIT` | `60` | Wartezeit nach Container-Restart |
| `CURL_TIMEOUT` | `15` | Timeout pro curl-Request |
| `TRAEFIK_CONTAINER` | `traefik` | Traefik-Container (wird übersprungen) |
| `WATCHDOG_CONTAINER` | `traeffik-sentinel` | Eigener Container (wird übersprungen) |
| `DEFAULT_SCHEME` | `https` | Fallback-Schema |

## Image aus Registry

```yaml
services:
  watchdog:
    image: ghcr.io/tannerap/traeffik-sentinel:latest
    container_name: traeffik-sentinel
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```
