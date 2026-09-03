#!/usr/bin/env python3
"""Bulk-create Uptime Kuma monitors for every currently running homeserver
container, plus an ntfy notification provider reusing the existing
homeserver-alerts topic. Safe to re-run -- skips anything that already
exists by name.

Run with: uv run services/uptime-kuma/setup-monitors.py
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["uptime-kuma-api>=1.2.1"]
# ///

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

from uptime_kuma_api import DockerType, MonitorType, NotificationType, UptimeKumaApi

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent.parent
CLAMAV_ENV = REPO_ROOT / "services" / "clamav" / ".env"

DOCKER_HOST_NAME = "homeserver"
NOTIFICATION_NAME = "ntfy-homeserver-alerts"
NTFY_SERVER_URL = "http://ntfy"
NTFY_TOPIC = "homeserver-alerts"

# Monitoring itself is circular -- if uptime-kuma is down, it can't alert
# about itself anyway.
EXCLUDE_CONTAINERS = {"uptime-kuma", "uptime-kuma-db"}


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:3001", help="Uptime Kuma base URL (default: %(default)s)")
    parser.add_argument("--interval", type=int, default=60, help="Heartbeat interval in seconds (default: %(default)s)")
    args = parser.parse_args()

    containers = running_containers()
    if not containers:
        print("No running containers found (besides uptime-kuma itself). Nothing to do.")
        return
    print(f"Found {len(containers)} running container(s) to monitor.")

    token = load_ntfy_token()
    if not token:
        print(f"Warning: could not read NTFY_ALERT_TOKEN from {CLAMAV_ENV} -- notification provider will be skipped.")

    username = input("Uptime Kuma username: ").strip()
    password = getpass.getpass("Uptime Kuma password: ")

    api = UptimeKumaApi(args.url, timeout=30)
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
        for name in containers:
            if name in existing_names:
                skipped += 1
                continue
            api.add_monitor(
                type=MonitorType.DOCKER,
                name=name,
                docker_container=name,
                docker_host=host_id,
                interval=args.interval,
                notificationIDList=notification_id_list,
            )
            created += 1
            print(f"  + {name}")

        print(f"\nDone. Created {created} monitor(s), skipped {skipped} already-existing.")
    finally:
        api.disconnect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
