#!/usr/bin/env python3
"""Bulk-create Beszel network monitors (response-time probes, new in 0.20.0)
on this host's agent. Safe to re-run -- skips any monitor whose
protocol/target/port already exists on the chosen system.

Default set: ICMP to 1.1.1.1 (WAN) and the LAN gateway (read from the
default route), a DNS lookup of ${DOMAIN}, HTTPS to ${DOMAIN} plus a few key
subdomains (the full Cloudflare tunnel -> nginx path), and TCP to those same
services' published ports on localhost (direct, bypassing the proxy -- works
because beszel-agent runs with network_mode: host).

Goes through the hub's REST API rather than the SQLite DB directly: the hub's
own record hooks are what push a new monitor out to the agent.

Run with: uv run services/beszel/setup-monitors.py [--system NAME] [--interval 60]
"""
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///

import argparse
import getpass
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent.parent
ROOT_ENV = REPO_ROOT / ".env"

WAN_TARGET = "1.1.1.1"

# (subdomain or "" for the apex, local published port or None)
HTTP_SERVICES = [
    ("", None),  # landing
    ("nextcloud", 8081),
    ("immich", 2283),
    ("vaultwarden", 8200),
]


def load_domain() -> str:
    if ROOT_ENV.exists():
        for line in ROOT_ENV.read_text().splitlines():
            if line.startswith("DOMAIN="):
                return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit(f"DOMAIN not set in {ROOT_ENV}")


def default_gateway() -> str | None:
    try:
        out = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    parts = out.split()
    return parts[parts.index("via") + 1] if "via" in parts else None


def build_monitors(domain: str) -> list[tuple[str, str, int]]:
    monitors = [("icmp", WAN_TARGET, 0)]
    gateway = default_gateway()
    if gateway:
        monitors.append(("icmp", gateway, 0))
    else:
        print("! no default gateway found -- skipping the LAN router ICMP monitor")
    monitors.append(("dns", domain, 0))
    for sub, _ in HTTP_SERVICES:
        monitors.append(("http", f"https://{sub + '.' if sub else ''}{domain}", 0))
    for _, port in HTTP_SERVICES:
        if port:
            monitors.append(("tcp", "localhost", port))
    return monitors


class Hub:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.token = None

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = self.token
        req = urllib.request.Request(
            self.url + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)

    def login(self, email: str, password: str) -> None:
        self.token = self.call(
            "POST", "/api/collections/users/auth-with-password", {"identity": email, "password": password}
        )["token"]

    def records(self, collection: str, filter_: str = "") -> list[dict]:
        query = urllib.parse.urlencode({"perPage": 500, **({"filter": filter_} if filter_ else {})})
        return self.call("GET", f"/api/collections/{collection}/records?{query}")["items"]


def pick_system(hub: Hub, name: str | None) -> dict:
    systems = hub.records("systems")
    if name:
        matches = [s for s in systems if s["name"] == name]
        if not matches:
            sys.exit(f"No system named {name!r} -- available: {', '.join(s['name'] for s in systems)}")
        return matches[0]
    if len(systems) == 1:
        return systems[0]
    if not systems:
        sys.exit("No systems in the hub yet -- pair an agent first (see docs/services/beszel.md)")
    sys.exit(f"Multiple systems -- pick one with --system: {', '.join(s['name'] for s in systems)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:8106", help="Beszel hub base URL (default: %(default)s)")
    parser.add_argument("--system", help="Hub system name to run the probes (default: the only system, if just one)")
    parser.add_argument("--interval", type=int, default=60, help="Probe interval in seconds (default: %(default)s)")
    args = parser.parse_args()

    monitors = build_monitors(load_domain())
    hub = Hub(args.url)
    email = input("Beszel login email: ")
    try:
        hub.login(email, getpass.getpass("Beszel password: "))
    except urllib.error.HTTPError as e:
        sys.exit(f"Login failed ({e.code}) -- check the email/password")
    except urllib.error.URLError as e:
        sys.exit(f"Can't reach the hub at {args.url}: {e.reason}")

    system = pick_system(hub, args.system)
    print(f"System: {system['name']} ({system['id']})")
    existing = {
        (m["protocol"], m["target"], m.get("port") or 0)
        for m in hub.records("network_monitors", f'system="{system["id"]}"')
    }

    added = skipped = failed = 0
    for proto, target, port in monitors:
        label = f"{proto:4} {target}{f':{port}' if port else ''}"
        if (proto, target, port) in existing:
            print(f"= exists  {label}")
            skipped += 1
            continue
        body = {"system": system["id"], "protocol": proto, "target": target, "interval": args.interval, "enabled": True}
        if port:
            body["port"] = port
        try:
            hub.call("POST", "/api/collections/network_monitors/records", body)
            print(f"+ added   {label}")
            added += 1
        except urllib.error.HTTPError as e:
            print(f"! failed  {label}: {e.code} {e.read().decode()}")
            failed += 1

    print(f"\n{added} added, {skipped} already existed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
