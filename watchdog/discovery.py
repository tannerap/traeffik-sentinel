"""Discover monitoring targets from Traefik Docker labels."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

import docker

logger = logging.getLogger("watchdog")

ROUTER_RULE_SUFFIX = ".rule"
ROUTER_ENTRYPOINTS_SUFFIX = ".entrypoints"
ROUTER_TLS_SUFFIX = ".tls"
ROUTER_PREFIX = "traefik.http.routers."

WATCHDOG_ENABLE_LABELS = ("watchdog.enable", "traefik.watchdog.enable")
HOST_PATTERN = re.compile(r"Host\(`([^`]+)`\)", re.IGNORECASE)
PATH_PREFIX_PATTERN = re.compile(r"PathPrefix\(`([^`]+)`\)", re.IGNORECASE)
SECURE_ENTRYPOINTS = frozenset({"websecure", "https", "tls"})


@dataclass(frozen=True)
class Target:
    url: str
    container: str
    router: str


def _router_name_from_label(label_key: str, suffix: str) -> str | None:
    if not label_key.startswith(ROUTER_PREFIX) or not label_key.endswith(suffix):
        return None
    return label_key[len(ROUTER_PREFIX) : -len(suffix)]


def _parse_hosts_and_path(rule: str) -> list[tuple[str, str | None]]:
    hosts = HOST_PATTERN.findall(rule)
    if not hosts:
        return []

    path_match = PATH_PREFIX_PATTERN.search(rule)
    path_prefix = path_match.group(1) if path_match else None
    if path_prefix and not path_prefix.startswith("/"):
        path_prefix = f"/{path_prefix}"

    return [(host, path_prefix) for host in hosts]


def _uses_https(entrypoints: str | None, tls_enabled: bool | None) -> bool:
    if tls_enabled:
        return True
    if not entrypoints:
        return os.getenv("DEFAULT_SCHEME", "https").lower() == "https"

    for entrypoint in entrypoints.split(","):
        if entrypoint.strip().lower() in SECURE_ENTRYPOINTS:
            return True
    return False


def _build_url(host: str, path_prefix: str | None, use_https: bool) -> str:
    scheme = "https" if use_https else "http"
    return f"{scheme}://{host}{path_prefix or ''}"


def _is_watchdog_enabled(labels: dict[str, str]) -> bool:
    for key in WATCHDOG_ENABLE_LABELS:
        if labels.get(key, "").lower() == "true":
            return True
    return False


def _should_skip_container(
    container_name: str,
    labels: dict[str, str],
    skip_names: set[str],
) -> bool:
    if container_name in skip_names:
        return True

    if labels.get("watchdog.enable", "").lower() == "false":
        return True

    if labels.get("traefik.enable", "true").lower() == "false":
        return True

    return not _is_watchdog_enabled(labels)


def _extract_router_labels(labels: dict[str, str]) -> dict[str, dict[str, str | bool]]:
    routers: dict[str, dict[str, str | bool]] = {}

    for key, value in labels.items():
        router_name = _router_name_from_label(key, ROUTER_RULE_SUFFIX)
        if router_name is not None:
            routers.setdefault(router_name, {})["rule"] = value
            continue

        router_name = _router_name_from_label(key, ROUTER_ENTRYPOINTS_SUFFIX)
        if router_name is not None:
            routers.setdefault(router_name, {})["entrypoints"] = value
            continue

        router_name = _router_name_from_label(key, ROUTER_TLS_SUFFIX)
        if router_name is not None:
            routers.setdefault(router_name, {})["tls"] = value.lower() == "true"

    return routers


def discover_targets(
    client: docker.DockerClient,
    *,
    skip_containers: set[str] | None = None,
) -> list[Target]:
    """Build monitoring targets from Traefik router labels on running containers."""
    skip_names = skip_containers or set()
    discovered: list[Target] = []
    seen_urls: set[str] = set()

    for container in client.containers.list():
        labels = container.labels or {}
        container_name = container.name

        if _should_skip_container(container_name, labels, skip_names):
            continue

        routers = _extract_router_labels(labels)
        if not routers:
            continue

        for router_name, router_config in routers.items():
            rule = router_config.get("rule")
            if not isinstance(rule, str):
                continue

            entrypoints = router_config.get("entrypoints")
            tls_value = router_config.get("tls")
            tls_enabled = tls_value if isinstance(tls_value, bool) else None
            entrypoints_str = entrypoints if isinstance(entrypoints, str) else None
            use_https = _uses_https(entrypoints_str, tls_enabled)

            for host, path_prefix in _parse_hosts_and_path(rule):
                url = _build_url(host, path_prefix, use_https)
                if url in seen_urls:
                    continue

                seen_urls.add(url)
                discovered.append(
                    Target(url=url, container=container_name, router=router_name)
                )
                logger.debug(
                    "Discovered target %s -> %s (router: %s)",
                    url,
                    container_name,
                    router_name,
                )

    discovered.sort(key=lambda target: (target.container, target.url))
    return discovered
