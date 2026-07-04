# traeffik-sentinel

Docker-Watchdog-Container zur Überwachung öffentlicher Web-Dienste hinter Traefik. Bei Ausfällen werden betroffene Container automatisch neu gestartet; bei anhaltenden Fehlern wird Traefik neu gestartet.

## Funktionsweise

1. Aktive **curl-Checks** gegen konfigurierte öffentliche URLs (Erreichbarkeit via Traefik)
2. Bei Fehler: `docker restart` des zugehörigen Containers
3. 60 Sekunden warten und erneut prüfen
4. Bei anhaltendem Fehler: `docker restart traefik`

## Schnellstart

```bash
cp config/targets.json.example config/targets.json
# URLs und Container-Namen in config/targets.json anpassen

docker compose up -d --build
```

## Konfiguration

### Ziele (`config/targets.json`)

```json
{
  "targets": [
    {
      "url": "https://app.example.com",
      "container": "my-app"
    }
  ]
}
```

### Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `CONFIG_PATH` | `/app/config/targets.json` | Pfad zur Ziel-Konfiguration |
| `CHECK_INTERVAL` | `300` | Sekunden zwischen Prüfzyklen |
| `RETRY_WAIT` | `60` | Wartezeit nach Container-Restart |
| `CURL_TIMEOUT` | `15` | Timeout pro curl-Request (Sekunden) |
| `TRAEFIK_CONTAINER` | `traefik` | Name des Traefik-Containers |

## Voraussetzungen

- Docker Socket (`/var/run/docker.sock`) muss gemountet sein
- Container-Namen in der Konfiguration müssen mit den tatsächlichen Docker-Containern übereinstimmen
- URLs müssen von innerhalb des Watchdog-Containers erreichbar sein (öffentliche Traefik-Routen)

## CI/CD

Bei jedem Push auf `main` baut die GitHub Actions Pipeline (`.github/workflows/build.yml`) das Image und pusht es nach:

```
ghcr.io/tannerap/traeffik-sentinel:latest
ghcr.io/tannerap/traeffik-sentinel:<git-sha>
```

## Image aus Registry nutzen

```yaml
services:
  watchdog:
    image: ghcr.io/tannerap/traeffik-sentinel:latest
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./config/targets.json:/app/config/targets.json:ro
```
