# traeffik-sentinel

Docker-Watchdog für Web-Dienste hinter Traefik.

## Schnellstart

```bash
docker compose up -d --build
```

Nur Container mit **`watchdog.enable=true`** werden überwacht. Portainer, Traefik und der Watchdog selbst werden ignoriert.

## Labels am App-Container

```yaml
labels:
  - watchdog.enable=true
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
| `SKIP_CONTAINERS` | `traefik,portainer,traeffik-sentinel` | Nie überwachen/neu starten |
| `ENABLE_TRAEFIK_RESTART` | `false` | Traefik bei anhaltendem Fehler neu starten |
| `TRAEFIK_CONTAINER` | `traefik` | Name des Traefik-Containers |
| `WATCHDOG_CONTAINER` | `traeffik-sentinel` | Eigener Container |

## Portainer not erreichbar?

Watchdog stoppen, dann Infrastruktur hochfahren:

```bash
docker stop traeffik-sentinel
docker start traefik portainer
```
