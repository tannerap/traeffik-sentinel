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
DEFAULT_SKIP_CONTAINERS = "traefik,portainer,traeffik-sentinel"

logger = logging.getLogger("watchdog")


def parse_skip_containers(raw: str, traefik_container: str, watchdog_container: str) -> set[str]:
    names = {name.strip() for name in raw.split(",") if name.strip()}
    names.update({traefik_container, watchdog_container})
    return names


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


GATEWAY_FAILURE_CODES = frozenset({502, 503, 504})


def _is_healthy_status(status_code: str) -> bool:
    """Treat any HTTP response as healthy except Traefik/backend gateway failures."""
    if not status_code.isdigit():
        return False

    code = int(status_code)
    if code < 100:
        return False

    return code not in GATEWAY_FAILURE_CODES


def check_url(url: str, timeout: int) -> bool:
    """Perform an active curl check against the public URL."""
    try:
        result = subprocess.run(
            [
                "curl",
                "-sS",
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

    status_code = result.stdout.strip()
    if _is_healthy_status(status_code):
        logger.info("OK %s (HTTP %s)", url, status_code)
        return True

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            logger.warning("curl error for %s: %s", url, stderr)
        return False

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
    *,
    enable_traefik_restart: bool,
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

    if not enable_traefik_restart:
        logger.warning(
            "Skipping Traefik restart for %s (ENABLE_TRAEFIK_RESTART=false)",
            target.url,
        )
        return

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
    *,
    enable_traefik_restart: bool,
) -> None:
    targets = discover_targets(client, skip_containers=skip_containers)

    if not targets:
        logger.info(
            "No watchdog targets discovered. Add label watchdog.enable=true "
            "to containers that should be monitored."
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
            enable_traefik_restart=enable_traefik_restart,
        )


def main() -> None:
    setup_logging()

    check_interval = int(os.getenv("CHECK_INTERVAL", str(DEFAULT_CHECK_INTERVAL)))
    retry_wait = int(os.getenv("RETRY_WAIT", str(DEFAULT_RETRY_WAIT)))
    curl_timeout = int(os.getenv("CURL_TIMEOUT", str(DEFAULT_CURL_TIMEOUT)))
    traefik_container = os.getenv("TRAEFIK_CONTAINER", DEFAULT_TRAEFIK_CONTAINER)
    watchdog_container = os.getenv("WATCHDOG_CONTAINER", DEFAULT_WATCHDOG_CONTAINER)
    skip_containers = parse_skip_containers(
        os.getenv("SKIP_CONTAINERS", DEFAULT_SKIP_CONTAINERS),
        traefik_container,
        watchdog_container,
    )
    enable_traefik_restart = (
        os.getenv("ENABLE_TRAEFIK_RESTART", "false").lower() == "true"
    )

    if check_interval <= 0:
        raise ValueError("CHECK_INTERVAL must be greater than 0")
    if retry_wait <= 0:
        raise ValueError("RETRY_WAIT must be greater than 0")

    logger.info(
        "Watchdog started (uid=%s, interval=%ss, retry_wait=%ss, traefik=%s, "
        "traefik_restart=%s, skip=%s)",
        os.getuid(),
        check_interval,
        retry_wait,
        traefik_container,
        enable_traefik_restart,
        ",".join(sorted(skip_containers)),
    )

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("Unable to connect to Docker socket: %s", exc)
        sys.exit(1)

    while True:
        try:
            run_cycle(
                client,
                skip_containers,
                traefik_container,
                retry_wait,
                curl_timeout,
                enable_traefik_restart=enable_traefik_restart,
            )
        except Exception:
            logger.exception("Unexpected error during health check cycle")

        logger.info("Sleeping for %s seconds until next cycle", check_interval)
        time.sleep(check_interval)


if __name__ == "__main__":
    main()
