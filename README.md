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
docker compose up -d --build
```

### Portainer

Wenn beim Recreate `unable to find user watchdog` erscheint, den alten Container **löschen** und den Stack mit `portainer-stack.yml` neu deployen. Wichtig: `user: "0:0"` muss gesetzt sein.

```bash
# In Portainer: Stacks → Add stack → Web editor
# Inhalt von portainer-stack.yml einfügen
```

Das Image enthält den `watchdog`-User als Fallback für alte Portainer-Konfigurationen. Der Entrypoint wechselt bei Bedarf per `gosu` auf root für den Docker-Socket-Zugriff.

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

- Docker Socket (`/var/run/docker.sock`) muss gemountet sein (wie bei Traefik)
- Der Prozess läuft als root (direkt oder via Entrypoint/`gosu`) für Socket-Zugriff
- Überwachte Container müssen Traefik-Router-Labels mit `Host(...)` besitzen
- URLs müssen von innerhalb des Watchdog-Containers erreichbar sein (öffentliche Traefik-Routen)

### Portainer: `unable to find user watchdog`

1. Container `traeffik-sentinel` in Portainer **entfernen** (nicht nur Recreate)
2. Stack mit `user: "0:0"` neu deployen (siehe `portainer-stack.yml`)
3. Neues Image ziehen: `docker pull ghcr.io/tannerap/traeffik-sentinel:latest`

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
    user: "0:0"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      TRAEFIK_CONTAINER: traefik
      WATCHDOG_CONTAINER: traeffik-sentinel
```
