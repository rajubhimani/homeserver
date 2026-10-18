"""Which Uptime Kuma Docker-container monitors setup-monitors.py must delete (pure, stdlib only, tested).

A monitor for a container that no longer exists is permanently "down" and teaches you to ignore red. They
survive because Kuma's data survives (and an old snapshot restores them): `clamav-watchdog` was removed on
2026-10-03 and was still red on 2026-10-06 after the Oct 3 snapshot came back.
"""

from __future__ import annotations

# Containers that were removed on purpose. Never monitored, and any monitor for them is deleted on every run,
# --prune or not, so restoring an old snapshot can't bring the red entry back for longer than one run.
RETIRED_CONTAINERS = {
    "clamav-watchdog": "removed 2026-10-03 (a curl loop on the Docker socket); Uptime Kuma's own clamav monitor replaces it",
}


def monitors_to_delete(existing: list[dict], known: set[str], excluded: set[str], host_id, docker_type, prune: bool,
                       one_shots: set[str] | None = None) -> list[tuple[dict, str]]:
    """-> [(monitor, why)] among the Docker Container monitors on the homeserver docker host.
    Retired containers always go; with `prune`, so does every monitor whose container is not defined in
    any compose.yml (`known`), or is a one-shot that exits by design. Hand-made HTTP/keyword/etc. monitors
    and monitors on other docker hosts are never touched."""
    out = []
    for m in existing:
        if m.get("type") != docker_type or m.get("docker_host") != host_id:
            continue
        name = m["name"]
        if name in RETIRED_CONTAINERS:
            out.append((m, f"retired: {RETIRED_CONTAINERS[name]}"))
        elif prune and name not in known and name not in excluded:
            out.append((m, "one-shot init container, exits by design" if name in (one_shots or set())
                        else "no longer defined in any compose.yml"))
    return out


def should_create(name: str) -> bool:
    return name not in RETIRED_CONTAINERS
