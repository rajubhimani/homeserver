#!/usr/bin/env python3
"""Bulk-create Uptime Kuma monitors for homeserver containers, plus an ntfy
notification provider reusing the existing homeserver-alerts topic. Safe to
re-run -- skips anything that already exists by name.

Default mode only covers currently-running containers (docker ps), all
enabled. --all instead discovers every container defined across every
services/*/compose.yml -- including ones not currently started -- and
creates a monitor for each: enabled for min/core tier (the always-on
services), disabled for daily/office/automation-ai/extra/manual (opt-in
tiers, so a stopped-on-purpose service doesn't trigger false down alerts) --
flip a monitor's Active toggle by hand later if you start using one of those
regularly.

Run with: uv run services/uptime-kuma/setup-monitors.py [--all]
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["uptime-kuma-api>=1.2.1"]
# ///

import argparse
import getpass
import json
import re
import subprocess
import sys
from pathlib import Path

from uptime_kuma_api import DockerType, MonitorType, NotificationType, UptimeKumaApi

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent.parent
CLAMAV_ENV = REPO_ROOT / "services" / "clamav" / ".env"
SERVICES_JSON = REPO_ROOT / "services.json"

DOCKER_HOST_NAME = "homeserver"
NOTIFICATION_NAME = "ntfy-homeserver-alerts"
NTFY_SERVER_URL = "http://ntfy"
NTFY_TOPIC = "homeserver-alerts"

ALWAYS_ON_TIERS = {"min", "core"}

# Monitoring itself is circular -- if uptime-kuma is down, it can't alert
# about itself anyway.
EXCLUDE_CONTAINERS = {"uptime-kuma", "uptime-kuma-db"}

# services/nginx/ is nginx-proxy-manager, a mutually-exclusive alternative to
# nginx-plain (only one proxy runs at a time) -- not part of any tier.
EXCLUDE_SERVICE_DIRS = {"nginx"}

# One-shot init/permission-fixing containers (restart: "no" in their own
# compose.yml) -- these are *supposed* to exit after running once, so a
# Docker Container monitor expecting them to stay "running" would be
# permanently, misleadingly "down". Not real long-running services.
EXCLUDE_ONE_SHOT = {
    "appflowy-minio-setup",
    "airflow-init",
    "plane-migrator",
    "firefly-permissions",
    "temporal-schema-setup",
    "temporal-create-namespace",
    "syncthing-permissions",
    "rocketchat-mongodb-fix-permission",
    "rocketchat-mongodb-init",
}


def load_ntfy_token() -> str | None:
    if not CLAMAV_ENV.exists():
        return None
    for line in CLAMAV_ENV.read_text().splitlines():
        if line.startswith("NTFY_ALERT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def running_containers() -> list[str]:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    names = sorted(n for n in result.stdout.splitlines() if n and n not in EXCLUDE_CONTAINERS)
    return names


def all_defined_containers() -> dict[str, str]:
    """Every container_name in every services/*/compose*.yml, mapped to its
    service directory's tier (from services.json). Covers containers that
    aren't currently running, not just the live set from `docker ps`."""
    data = json.loads(SERVICES_JSON.read_text())
    services = data.get("services", data)
    tier_by_slug = {s["slug"]: s["tier"] for s in services if "slug" in s and "tier" in s and not s.get("virtual")}

    container_to_tier: dict[str, str] = {}
    for svc_dir in sorted((REPO_ROOT / "services").iterdir()):
        if not svc_dir.is_dir() or svc_dir.name in EXCLUDE_SERVICE_DIRS:
            continue
        tier = tier_by_slug.get(svc_dir.name)
        if not tier:
            continue
        for compose_file in list(svc_dir.glob("compose.yml")) + list(svc_dir.glob("docker-compose.yml")):
            for m in re.finditer(r"container_name:\s*(\S+)", compose_file.read_text()):
                name = m.group(1).strip().strip("\"'")
                if name in EXCLUDE_CONTAINERS or name in EXCLUDE_ONE_SHOT:
                    continue
                container_to_tier.setdefault(name, tier)
    return container_to_tier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3001", help="Uptime Kuma base URL (default: %(default)s)")
    parser.add_argument("--interval", type=int, default=60, help="Heartbeat interval in seconds (default: %(default)s)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Cover every container defined in the repo, not just currently-running ones. "
        "Enabled for min/core tier, created disabled for everything else.",
    )
    args = parser.parse_args()

    if args.all:
        container_tiers = all_defined_containers()
        if not container_tiers:
            print("No containers discovered across services/*/compose.yml. Nothing to do.")
            return
        enabled_count = sum(1 for t in container_tiers.values() if t in ALWAYS_ON_TIERS)
        print(
            f"Discovered {len(container_tiers)} container(s) across the whole repo "
            f"({enabled_count} min/core -> enabled, {len(container_tiers) - enabled_count} other tiers -> created disabled)."
        )
    else:
        running = running_containers()
        if not running:
            print("No running containers found (besides uptime-kuma itself). Nothing to do.")
            return
        container_tiers = {name: "min" for name in running}  # tier value only used for the active/disabled decision below
        print(f"Found {len(running)} running container(s) to monitor.")

    token = load_ntfy_token()
    if not token:
        print(f"Warning: could not read NTFY_ALERT_TOKEN from {CLAMAV_ENV} -- notification provider will be skipped.")

    username = input("Uptime Kuma username: ").strip()
    password = getpass.getpass("Uptime Kuma password: ")

    api = UptimeKumaApi(args.url, timeout=60)
    try:
        api.login(username, password)
        print("Logged in.")

        hosts = api.get_docker_hosts()
        host = next((h for h in hosts if h["name"] == DOCKER_HOST_NAME), None)
        if host:
            host_id = host["id"]
            print(f"Reusing existing docker host '{DOCKER_HOST_NAME}' (id={host_id}).")
        else:
            result = api.add_docker_host(
                name=DOCKER_HOST_NAME,
                dockerType=DockerType.SOCKET,
                dockerDaemon="/var/run/docker.sock",
            )
            host_id = result["id"]
            print(f"Created docker host '{DOCKER_HOST_NAME}' (id={host_id}).")

        notif_id = None
        if token:
            notifications = api.get_notifications()
            existing = next((n for n in notifications if n["name"] == NOTIFICATION_NAME), None)
            if existing:
                notif_id = existing["id"]
                print(f"Reusing existing notification '{NOTIFICATION_NAME}' (id={notif_id}).")
            else:
                result = api.add_notification(
                    name=NOTIFICATION_NAME,
                    isDefault=True,
                    applyExisting=True,
                    type=NotificationType.NTFY,
                    ntfyserverurl=NTFY_SERVER_URL,
                    ntfytopic=NTFY_TOPIC,
                    ntfyAuthenticationMethod="accessToken",
                    ntfyaccesstoken=token,
                    ntfyPriority=4,
                )
                notif_id = result["id"]
                print(f"Created notification provider '{NOTIFICATION_NAME}' (id={notif_id}).")

        notification_id_list = {str(notif_id): True} if notif_id else {}

        existing_monitors = api.get_monitors()
        existing_names = {m["name"] for m in existing_monitors}

        created = 0
        skipped = 0
        for name, tier in sorted(container_tiers.items()):
            if name in existing_names:
                skipped += 1
                continue
            active = tier in ALWAYS_ON_TIERS
            result = api.add_monitor(
                type=MonitorType.DOCKER,
                name=name,
                docker_container=name,
                docker_host=host_id,
                interval=args.interval,
                notificationIDList=notification_id_list,
                resendInterval=30,
            )
            if not active:
                # Active/paused isn't an editMonitor field -- it's a separate
                # pauseMonitor/resumeMonitor event. New monitors come back
                # enabled by default, so pause it as a follow-up call.
                api.pause_monitor(result["monitorID"])
            created += 1
            print(f"  + {name}{'' if active else '  (disabled, tier=' + tier + ')'}")

        print(f"\nDone. Created {created} monitor(s), skipped {skipped} already-existing.")
    finally:
        api.disconnect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
