#!/usr/bin/env python3
"""Docker Watchdog: monitors public URLs via Traefik and restarts containers on failure."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

import docker
from docker.errors import DockerException, NotFound

from discovery import Target, discover_targets

DEFAULT_CHECK_INTERVAL = 300
DEFAULT_RETRY_WAIT = 60
DEFAULT_CURL_TIMEOUT = 15
DEFAULT_TRAEFIK_CONTAINER = "traefik"
DEFAULT_WATCHDOG_CONTAINER = "traeffik-sentinel"

logger = logging.getLogger("watchdog")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def check_url(url: str, timeout: int) -> bool:
    """Perform an active curl check against the public URL."""
    try:
        result = subprocess.run(
            [
                "curl",
                "-fsS",
                "-o",
                "/dev/null",
                "-w",
                "%{http_code}",
                "--max-time",
                str(timeout),
                "-L",
                url,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout + 5,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("curl check failed for %s: %s", url, exc)
        return False

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            logger.warning("curl error for %s: %s", url, stderr)
        return False

    status_code = result.stdout.strip()
    if status_code.startswith(("2", "3")):
        logger.info("OK %s (HTTP %s)", url, status_code)
        return True

    logger.warning("Unexpected HTTP status for %s: %s", url, status_code or "unknown")
    return False


def restart_container(client: docker.DockerClient, container_name: str) -> None:
    try:
        container = client.containers.get(container_name)
    except NotFound as exc:
        raise RuntimeError(f"Container '{container_name}' not found") from exc

    logger.warning("Restarting container '%s' ...", container_name)
    container.restart(timeout=30)
    logger.info("Container '%s' restarted successfully", container_name)


def handle_target_failure(
    client: docker.DockerClient,
    target: Target,
    traefik_container: str,
    retry_wait: int,
    curl_timeout: int,
) -> None:
    logger.error(
        "Target unreachable: %s (container: %s, router: %s)",
        target.url,
        target.container,
        target.router,
    )

    try:
        restart_container(client, target.container)
    except (DockerException, RuntimeError) as exc:
        logger.error("Failed to restart '%s': %s", target.container, exc)
        return

    logger.info("Waiting %s seconds before re-checking %s", retry_wait, target.url)
    time.sleep(retry_wait)

    if check_url(target.url, curl_timeout):
        logger.info(
            "Recovery successful for %s after restarting '%s'",
            target.url,
            target.container,
        )
        return

    logger.error(
        "Target still unreachable after container restart: %s",
        target.url,
    )

    try:
        restart_container(client, traefik_container)
    except (DockerException, RuntimeError) as exc:
        logger.error("Failed to restart Traefik '%s': %s", traefik_container, exc)


def run_cycle(
    client: docker.DockerClient,
    skip_containers: set[str],
    traefik_container: str,
    retry_wait: int,
    curl_timeout: int,
) -> None:
    targets = discover_targets(client, skip_containers=skip_containers)

    if not targets:
        logger.warning(
            "No Traefik targets discovered. Ensure containers expose "
            "traefik.http.routers.<name>.rule labels with Host(`...`)."
        )
        return

    logger.info("Starting health check cycle for %d target(s)", len(targets))
    for target in targets:
        logger.info(
            "Checking %s (container: %s, router: %s)",
            target.url,
            target.container,
            target.router,
        )
        if check_url(target.url, curl_timeout):
            continue
        handle_target_failure(
            client,
            target,
            traefik_container,
            retry_wait,
            curl_timeout,
        )


def main() -> None:
    setup_logging()

    check_interval = int(os.getenv("CHECK_INTERVAL", str(DEFAULT_CHECK_INTERVAL)))
    retry_wait = int(os.getenv("RETRY_WAIT", str(DEFAULT_RETRY_WAIT)))
    curl_timeout = int(os.getenv("CURL_TIMEOUT", str(DEFAULT_CURL_TIMEOUT)))
    traefik_container = os.getenv("TRAEFIK_CONTAINER", DEFAULT_TRAEFIK_CONTAINER)
    watchdog_container = os.getenv("WATCHDOG_CONTAINER", DEFAULT_WATCHDOG_CONTAINER)

    if check_interval <= 0:
        raise ValueError("CHECK_INTERVAL must be greater than 0")
    if retry_wait <= 0:
        raise ValueError("RETRY_WAIT must be greater than 0")

    skip_containers = {traefik_container, watchdog_container}
    logger.info(
        "Watchdog started (interval=%ss, retry_wait=%ss, traefik=%s, discovery=labels)",
        check_interval,
        retry_wait,
        traefik_container,
    )

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("Unable to connect to Docker socket: %s", exc)
        if "Permission denied" in str(exc):
            logger.error(
                "Docker socket permission denied. Add the container to the host "
                "docker group via group_add and set DOCKER_GID in .env, e.g. "
                'DOCKER_GID=$(getent group docker | cut -d: -f3)'
            )
        sys.exit(1)

    while True:
        try:
            run_cycle(
                client,
                skip_containers,
                traefik_container,
                retry_wait,
                curl_timeout,
            )
        except Exception:
            logger.exception("Unexpected error during health check cycle")

        logger.info("Sleeping for %s seconds until next cycle", check_interval)
        time.sleep(check_interval)


if __name__ == "__main__":
    main()
