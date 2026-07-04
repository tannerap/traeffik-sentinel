# traeffik-sentinel

A single Python service (`watchdog/watchdog.py`) that monitors public URLs behind Traefik via `curl` and, on failure, restarts the target container through the Docker socket — escalating to restarting Traefik if the target stays down. See `README.md` for the full description and configuration reference.

## Cursor Cloud specific instructions

### Services
There is only one service: the `watchdog` loop. It exposes no ports (outbound curl + Docker socket calls only) and has no database. There are no lint or test suites configured in this repo — the only CI step (`.github/workflows/build.yml`) just builds/pushes the Docker image.

### Docker daemon must be started manually
This VM has no systemd, so Docker does not auto-start. Start it once per session before running anything that needs Docker:
```
sudo dockerd > /tmp/dockerd.log 2>&1 &
```
(A tmux session named `dockerd` is used during setup for this.) Docker CLI needs `sudo` unless you start a fresh login shell after the `docker` group was added.

### Local dev run (primary workflow)
Dependencies are installed into `.venv` by the update script. `config/targets.json` is gitignored — create it from `config/targets.json.example` first. Then run:
```
cp -n config/targets.json.example config/targets.json   # edit URLs + container names
sudo env CONFIG_PATH=./config/targets.json CHECK_INTERVAL=300 RETRY_WAIT=60 .venv/bin/python watchdog/watchdog.py
```
`sudo` is required because `docker.from_env()` needs access to `/var/run/docker.sock`. Use small `CHECK_INTERVAL`/`RETRY_WAIT` values when testing so a full check→restart→escalate cycle completes quickly.

### Containerized run (`docker compose up -d --build`)
The image runs as the non-root `watchdog` user. The mounted host socket `/var/run/docker.sock` is `root:docker` mode `0660`, so the in-container user cannot connect and the container will crash-loop with `PermissionError(13)`. For a dev/test run, loosen the socket first:
```
sudo chmod 666 /var/run/docker.sock
```
(Do NOT rely on this in production; there you would align the container user with the host `docker` gid instead.)

### Notes
- The watchdog `curl` check treats any non-2xx/3xx (including 404) and connection errors as a failure and triggers a container restart, then re-checks after `RETRY_WAIT`, then restarts `TRAEFIK_CONTAINER`.
- `docker restart` does not increment a container's `RestartCount` (that only counts crash restarts); verify watchdog-triggered restarts via `docker inspect -f '{{.State.StartedAt}}'` instead.
