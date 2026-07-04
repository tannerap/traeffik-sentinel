# traeffik-sentinel

Docker-Watchdog-Container zur Überwachung öffentlicher Web-Dienste hinter Traefik. Ziele werden automatisch aus **Traefik Docker-Labels** erkannt — keine separate URL-Konfiguration nötig.

## Funktionsweise

1. **Label-Discovery**: Liest laufende Container via Docker Socket und extrahiert URLs aus Traefik-Router-Labels
2. Aktive **curl-Checks** gegen die erkannten öffentlichen URLs (Erreichbarkeit via Traefik)
3. Bei Fehler: `docker restart` des zugehörigen Containers
4. 60 Sekunden warten und erneut prüfen
5. Bei anhaltendem Fehler: `docker restart traefik`

## Schnellstart

```bash
echo "DOCKER_GID=$(getent group docker | cut -d: -f3)" > .env
docker compose up -d --build
```

Der Host-`docker`-Gruppe GID wird benötigt, damit der nicht-root Container auf `/var/run/docker.sock` zugreifen kann.

Der Watchdog erkennt automatisch alle Container mit Traefik-Labels wie:

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.myapp.rule=Host(`app.example.com`)
  - traefik.http.routers.myapp.entrypoints=websecure
  - traefik.http.routers.myapp.tls=true
```

Aus diesen Labels wird die Prüf-URL `https://app.example.com` abgeleitet.

## Unterstützte Traefik-Labels

| Label | Verwendung |
|-------|------------|
| `traefik.enable` | Container mit `false` werden übersprungen |
| `traefik.http.routers.<name>.rule` | `Host(\`domain.tld\`)` und optional `PathPrefix(\`/api\`)` |
| `traefik.http.routers.<name>.entrypoints` | `websecure`/`https` → HTTPS, sonst HTTP |
| `traefik.http.routers.<name>.tls` | `true` → HTTPS |

Beispiel mit Pfad:

```yaml
traefik.http.routers.api.rule: Host(`api.example.com`) && PathPrefix(`/health`)
traefik.http.routers.api.entrypoints: websecure
```

→ Prüf-URL: `https://api.example.com/health`

## Umgebungsvariablen

| Variable | Standard | Beschreibung |
|----------|----------|--------------|
| `CHECK_INTERVAL` | `300` | Sekunden zwischen Prüfzyklen |
| `RETRY_WAIT` | `60` | Wartezeit nach Container-Restart |
| `CURL_TIMEOUT` | `15` | Timeout pro curl-Request (Sekunden) |
| `TRAEFIK_CONTAINER` | `traefik` | Name des Traefik-Containers (wird übersprungen) |
| `WATCHDOG_CONTAINER` | `traeffik-sentinel` | Eigener Container-Name (wird übersprungen) |
| `DEFAULT_SCHEME` | `https` | Fallback-Schema wenn Entrypoints/TLS fehlen |

## Voraussetzungen

- Docker Socket (`/var/run/docker.sock`) muss gemountet sein
- `DOCKER_GID` muss der GID der Host-`docker`-Gruppe entsprechen (siehe `.env.example`)
- Überwachte Container müssen Traefik-Router-Labels mit `Host(...)` besitzen
- URLs müssen von innerhalb des Watchdog-Containers erreichbar sein (öffentliche Traefik-Routen)

### Docker-Socket Berechtigungen

Der Container läuft als nicht-root User. Ohne passende Gruppenmitgliedschaft schlägt der Socket-Zugriff fehl:

```
PermissionError(13, 'Permission denied')
```

Lösung: `group_add` mit der Host-`docker`-GID setzen:

```bash
getent group docker   # z.B. docker:x:999:user
echo "DOCKER_GID=999" > .env
```

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
    container_name: traeffik-sentinel
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    group_add:
      - "999"  # Host docker group GID
    environment:
      TRAEFIK_CONTAINER: traefik
      WATCHDOG_CONTAINER: traeffik-sentinel
```
