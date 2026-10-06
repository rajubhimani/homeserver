#!/usr/bin/env python3
"""Bulk-create Uptime Kuma monitors for homeserver containers, plus an ntfy
notification provider reusing the existing homeserver-alerts topic. Safe to
re-run -- skips anything that already exists by name.

Default mode only covers currently-running containers (docker ps), all
enabled. --all instead discovers every container defined across every
services/*/compose.yml -- including ones not currently started -- and
creates a monitor for each: enabled for min/core tier (the always-on
services), disabled for daily/browser/office/automation-ai/extra/manual (opt-in
tiers, so a stopped-on-purpose service doesn't trigger false down alerts) --
flip a monitor's Active toggle by hand later if you start using one of those
regularly.

--prune (only with --all) also deletes this script's own Docker Container
monitors whose container no longer exists in any services/*/compose.yml --
i.e. a service that was removed or renamed -- or is a one-shot init
container (restart: "no"/on-failure), which exits by design and would
otherwise sit permanently "down". Re-run --all --prune after every
add/remove/rename so monitoring always matches the repo.

--k8s is the mode for the Kubernetes deployment (docs/17): Docker Container
monitors read the Docker socket, which pods don't have, so they all report
down. It plans monitors from the generated manifests instead (see
k8s_monitors.py): an HTTP check per public hostname, and a TCP check per
database and cache. Disabled for services the env doesn't run. With --prune
it also deletes the Docker Container monitors, which can't work there.

Run with: uv run services/uptime-kuma/setup-monitors.py [--all [--prune]]
          uv run services/uptime-kuma/setup-monitors.py --k8s [--prune] [--env prod]
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["uptime-kuma-api>=1.2.1", "pyyaml"]
# ///

import argparse
import getpass
import json
import re
import subprocess
import sys
from pathlib import Path

from uptime_kuma_api import DockerType, MonitorType, NotificationType, UptimeKumaApi

sys.path.insert(0, str(Path(__file__).resolve().parent))
from monitor_rules import monitors_to_delete, should_create  # noqa: E402

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent.parent
NTFY_ENV = REPO_ROOT / "services" / "ntfy" / ".env"
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

# One-shot init/permission-fixing containers are *supposed* to exit after
# running once, so a Docker Container monitor expecting them to stay
# "running" would be permanently, misleadingly "down". They're detected
# automatically from their own compose.yml -- any service whose restart
# policy is one of these runs to completion by design. (This used to be a
# hand-maintained name list; it silently drifted -- atuin-permissions,
# authentik-permissions and eight others got monitors that sat "down".)
ONE_SHOT_RESTART_POLICIES = {"no", "on-failure"}

_SERVICE_KEY = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*(#.*)?$")
_FIELD = re.compile(r"^    (container_name|restart):\s*[\"']?([^\"'\s#]+)")


def load_ntfy_token() -> str | None:
    if not NTFY_ENV.exists():
        return None
    for line in NTFY_ENV.read_text().splitlines():
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


def compose_containers(compose_file: Path) -> list[tuple[str, str]]:
    """(container_name, restart policy) for each service in a compose file.
    Line-based rather than a YAML dependency: every compose.yml here uses
    2-space service keys and 4-space fields under a top-level 'services:'."""
    result: list[tuple[str, str]] = []
    in_services = False
    current: dict[str, str] = {}

    def flush() -> None:
        if current.get("container_name"):
            result.append((current["container_name"], current.get("restart", "")))

    for line in compose_file.read_text().splitlines():
        if line and not line[0].isspace():  # top-level key
            flush()
            current = {}
            in_services = line.startswith("services:")
            continue
        if not in_services:
            continue
        if _SERVICE_KEY.match(line):
            flush()
            current = {}
        elif m := _FIELD.match(line):
            current[m.group(1)] = m.group(2)
    flush()
    return result


def all_defined_containers() -> tuple[dict[str, str], set[str]]:
    """Every container_name in every services/*/compose*.yml, mapped to its
    service directory's tier (from services.json). Covers containers that
    aren't currently running, not just the live set from `docker ps`.
    Also returns the one-shot containers that were left out (see
    ONE_SHOT_RESTART_POLICIES), so --prune can delete monitors for them."""
    data = json.loads(SERVICES_JSON.read_text())
    services = data.get("services", data)
    tier_by_slug = {s["slug"]: s["tier"] for s in services if "slug" in s and "tier" in s and not s.get("virtual")}

    container_to_tier: dict[str, str] = {}
    one_shots: set[str] = set()
    for svc_dir in sorted((REPO_ROOT / "services").iterdir()):
        if not svc_dir.is_dir() or svc_dir.name in EXCLUDE_SERVICE_DIRS:
            continue
        tier = tier_by_slug.get(svc_dir.name)
        if not tier:
            continue
        for compose_file in list(svc_dir.glob("compose.yml")) + list(svc_dir.glob("docker-compose.yml")):
            for name, restart in compose_containers(compose_file):
                if name in EXCLUDE_CONTAINERS:
                    continue
                if restart in ONE_SHOT_RESTART_POLICIES:
                    one_shots.add(name)
                    continue
                container_to_tier.setdefault(name, tier)
    return container_to_tier, one_shots


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
    parser.add_argument(
        "--prune",
        action="store_true",
        help="With --all: delete Docker Container monitors on the homeserver docker host whose "
        "container no longer exists in any services/*/compose.yml (removed/renamed services).",
    )
    parser.add_argument(
        "--keep-stale",
        action="store_true",
        help="With --all: don't delete monitors whose container no longer exists (by default --all prunes them: "
        "the compose files are the source of truth, and a red monitor for a removed container teaches you to ignore red).",
    )
    parser.add_argument("--k8s", action="store_true",
                        help="Kubernetes mode: HTTP checks on the public hostnames and TCP checks on the "
                        "databases/caches, planned from the generated manifests (see k8s_monitors.py).")
    parser.add_argument("--env", default="prod", help="With --k8s: which kubernetes/deploy/<env>.yaml decides what is enabled (default: %(default)s)")
    args = parser.parse_args()
    if args.k8s and args.all:
        parser.error("--k8s and --all are different modes")
    if args.prune and not (args.all or args.k8s):
        parser.error("--prune needs --all (without --all the script only sees running containers, "
                     "so every stopped service would look 'removed')")

    if args.k8s:
        sys.path.insert(0, str(SERVICE_DIR))
        import k8s_monitors
        plan = k8s_monitors.plan(args.env)
        print(f"Planned {len(plan)} monitor(s) for {args.env}: "
              f"{sum(m['kind'] == 'http' for m in plan)} public URL, {sum(m['kind'] == 'tcp' for m in plan)} TCP; "
              f"{sum(m['active'] for m in plan)} enabled.")
        container_tiers, one_shots = {}, set()
    elif args.all:
        container_tiers, one_shots = all_defined_containers()
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
        one_shots: set[str] = set()
        container_tiers = {name: "min" for name in running}  # tier value only used for the active/disabled decision below
        print(f"Found {len(running)} running container(s) to monitor.")

    token = load_ntfy_token()
    if not token:
        print(f"Warning: could not read NTFY_ALERT_TOKEN from {NTFY_ENV} -- notification provider will be skipped.")

    username = input("Uptime Kuma username: ").strip()
    password = getpass.getpass("Uptime Kuma password: ")

    api = UptimeKumaApi(args.url, timeout=60)
    try:
        # With 2FA enabled, a correct username/password doesn't raise -- the
        # server just answers {"tokenRequired": true} and leaves the socket
        # unauthenticated, so the next call (get_docker_hosts) waits 60s for
        # state that never comes and times out. Ask for the code and retry.
        result = api.login(username, password)
        if isinstance(result, dict) and result.get("tokenRequired"):
            token = input("Uptime Kuma 2FA code: ").strip()
            api.login(username, password, token)
        print("Logged in.")

        hosts = api.get_docker_hosts()
        host = next((h for h in hosts if h["name"] == DOCKER_HOST_NAME), None)
        if args.k8s:
            host_id = host["id"] if host else None  # only to find the Docker monitors to prune
        elif host:
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

        if args.k8s:
            created = skipped = pruned = 0
            for m in plan:
                if m["name"] in existing_names:
                    skipped += 1
                    continue
                common = dict(name=m["name"], interval=args.interval, notificationIDList=notification_id_list,
                              resendInterval=30)
                if m["kind"] == "http":
                    result = api.add_monitor(type=MonitorType.HTTP, url=m["url"], maxredirects=0,
                                             accepted_statuscodes=k8s_monitors.ACCEPTED_STATUS, **common)
                else:
                    result = api.add_monitor(type=MonitorType.PORT, hostname=m["hostname"], port=m["port"], **common)
                if not m["active"]:
                    api.pause_monitor(result["monitorID"])  # pausing is its own event, see below
                created += 1
                print(f"  + {m['name']}{'' if m['active'] else '  (disabled: ' + m['service'] + ' is not running)'}")
            if args.prune:
                for mon in existing_monitors:
                    if mon.get("type") == MonitorType.DOCKER and mon.get("docker_host") == host_id:
                        api.delete_monitor(mon["id"])
                        pruned += 1
                        print(f"  - {mon['name']}  (removed: Docker Container monitors can't work on Kubernetes)")
            print(f"\nDone. Created {created} monitor(s), skipped {skipped} already-existing, pruned {pruned} Docker monitor(s).")
            return

        created = 0
        skipped = 0
        for name, tier in sorted(container_tiers.items()):
            if not should_create(name):
                continue
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

        # Retired containers are deleted on every run; with --all (unless --keep-stale) or --prune, so is every
        # Docker monitor whose container no longer exists in any compose.yml (monitor_rules.py).
        prune = (args.all and not args.keep_stale) or args.prune
        pruned = 0
        for m, why in monitors_to_delete(existing_monitors, set(container_tiers), EXCLUDE_CONTAINERS, host_id,
                                         MonitorType.DOCKER, prune, one_shots):
            api.delete_monitor(m["id"])
            pruned += 1
            print(f"  - {m['name']}  (removed: {why})")

        print(f"\nDone. Created {created} monitor(s), skipped {skipped} already-existing, pruned {pruned} stale.")
    finally:
        api.disconnect()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
