#!/usr/bin/env python3
"""Docker Watchdog: monitors public URLs via Traefik and restarts containers on failure."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import docker
from docker.errors import DockerException, NotFound

DEFAULT_CONFIG_PATH = "/app/config/targets.json"
DEFAULT_CHECK_INTERVAL = 300
DEFAULT_RETRY_WAIT = 60
DEFAULT_CURL_TIMEOUT = 15
DEFAULT_TRAEFIK_CONTAINER = "traefik"

logger = logging.getLogger("watchdog")


@dataclass(frozen=True)
class Target:
    url: str
    container: str


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def load_targets(config_path: Path) -> list[Target]:
    with config_path.open(encoding="utf-8") as config_file:
        data: dict[str, Any] = json.load(config_file)

    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("Config must contain a non-empty 'targets' list")

    targets: list[Target] = []
    for index, entry in enumerate(raw_targets, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Target #{index} must be an object")

        url = entry.get("url")
        container = entry.get("container")
        if not url or not container:
            raise ValueError(f"Target #{index} requires 'url' and 'container'")

        targets.append(Target(url=str(url), container=str(container)))

    return targets


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
    logger.error("Target unreachable: %s (container: %s)", target.url, target.container)

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
    targets: list[Target],
    traefik_container: str,
    retry_wait: int,
    curl_timeout: int,
) -> None:
    logger.info("Starting health check cycle for %d target(s)", len(targets))

    for target in targets:
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

    config_path = Path(os.getenv("CONFIG_PATH", DEFAULT_CONFIG_PATH))
    check_interval = int(os.getenv("CHECK_INTERVAL", str(DEFAULT_CHECK_INTERVAL)))
    retry_wait = int(os.getenv("RETRY_WAIT", str(DEFAULT_RETRY_WAIT)))
    curl_timeout = int(os.getenv("CURL_TIMEOUT", str(DEFAULT_CURL_TIMEOUT)))
    traefik_container = os.getenv("TRAEFIK_CONTAINER", DEFAULT_TRAEFIK_CONTAINER)

    if check_interval <= 0:
        raise ValueError("CHECK_INTERVAL must be greater than 0")
    if retry_wait <= 0:
        raise ValueError("RETRY_WAIT must be greater than 0")

    logger.info("Loading targets from %s", config_path)
    targets = load_targets(config_path)
    logger.info(
        "Watchdog started (interval=%ss, retry_wait=%ss, traefik=%s)",
        check_interval,
        retry_wait,
        traefik_container,
    )

    try:
        client = docker.from_env()
    except DockerException as exc:
        logger.error("Unable to connect to Docker socket: %s", exc)
        sys.exit(1)

    while True:
        try:
            run_cycle(client, targets, traefik_container, retry_wait, curl_timeout)
        except Exception:
            logger.exception("Unexpected error during health check cycle")

        logger.info("Sleeping for %s seconds until next cycle", check_interval)
        time.sleep(check_interval)


if __name__ == "__main__":
    main()
