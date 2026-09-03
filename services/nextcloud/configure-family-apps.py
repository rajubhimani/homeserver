#!/usr/bin/env python3
"""Configure Nextcloud for family Drive/Calendar/Talk use on a fresh install.

Usage: uv run services/nextcloud/configure-family-apps.py   (from repo root)

Installs and enables the apps a family actually uses (Files, Calendar,
Contacts, Talk, Mail, Deck, Whiteboard, Office/ONLYOFFICE), wires up
ONLYOFFICE/Whiteboard/ClamAV integration from their own .env files if those
services are set up, disables the enterprise/business-bundle apps that add
no value for personal use (workflow automation, retention policies,
LDAP/SAML, social-media sharing, etc.), and turns off the global lookup
directory (privacy — nothing about a private family instance should be
published to it).

Safe to re-run any time (idempotent — every occ command here is itself
idempotent: install-if-missing, enable-if-disabled, disable-if-enabled).

Requires Nextcloud to already be past its own first-run install (this
script only runs `occ` commands, which need a working install). Bring it
up and finish the setup wizard / initial admin login first if this is a
truly fresh instance, then run this.

Background/rationale for each decision: docs/services/nextcloud.md
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent.parent

# Apps a family actually uses day to day -- installed/enabled unconditionally.
FAMILY_APPS = [
    "calendar",
    "contacts",
    "mail",
    "deck",
    "whiteboard",
    "onlyoffice",
]

# Enterprise/business-bundle apps that add nothing for personal/family use --
# see docs/services/nextcloud.md for the full reasoning per app.
APPS_TO_REMOVE = [
    "terms_of_service",
    "support",
    "socialsharing_diaspora",
    "socialsharing_facebook",
    "socialsharing_twitter",
    "socialsharing_email",
    "survey_client",
    "files_confidential",
    "files_retention",
    "files_automatedtagging",
    "files_downloadlimit",
    "user_ldap",
    "user_saml",
    "webhook_listeners",
    "nextcloud_announcements",
    "groupfolders",
    "circles",
    "tables",
    "forms",
    "collectives",
    "related_resources",
    "integration_forgejo_gitea",
]

# Nextcloud won't let these be removed (shipped/core) -- disabling is enough,
# they're inert with no config once disabled. app:disable is attempted for
# all of APPS_TO_REMOVE + these regardless; app:remove is only attempted for
# APPS_TO_REMOVE, and failures there ("shipped/core, cannot be removed") are
# expected and non-fatal.
SHIPPED_CANNOT_DISABLE = {"workflowengine", "cloud_federation_api"}


def load_env(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def occ(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec", "-u", "www-data", "nextcloud", "php", "occ", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  ! {' '.join(args)} -> {(result.stderr or result.stdout).strip()}")
    else:
        out = (result.stdout or result.stderr).strip()
        if out:
            print(f"  {out.splitlines()[0]}")
    return result


def require_nextcloud_installed() -> None:
    result = subprocess.run(
        ["docker", "exec", "nextcloud", "curl", "-sf", "http://localhost/status.php"],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or '"installed":true' not in result.stdout:
        sys.exit(
            "Nextcloud isn't up and installed yet. Run "
            "`uv run homeserver.py dev up nextcloud`, finish the first-run "
            "setup wizard (create the admin account), then re-run this script."
        )


def main() -> int:
    require_nextcloud_installed()
    root_env = load_env(REPO_ROOT / ".env")
    domain = root_env.get("DOMAIN")

    print("== Installing family apps ==")
    for app in FAMILY_APPS:
        occ("app:install", app, check=False)

    onlyoffice_env = load_env(REPO_ROOT / "services" / "onlyoffice" / ".env")
    if onlyoffice_env.get("JWT_SECRET") and domain:
        print("== Wiring ONLYOFFICE ==")
        occ("config:app:set", "onlyoffice", "DocumentServerUrl", "--value", f"https://onlyoffice.{domain}/")
        occ("config:app:set", "onlyoffice", "DocumentServerInternalUrl", "--value", "http://onlyoffice/")
        occ("config:app:set", "onlyoffice", "jwt_secret", "--value", onlyoffice_env["JWT_SECRET"])
    else:
        print("== Skipping ONLYOFFICE wiring (services/onlyoffice/.env not set up) ==")

    whiteboard_env = load_env(REPO_ROOT / "services" / "whiteboard" / ".env")
    if whiteboard_env.get("JWT_SECRET_KEY") and domain:
        print("== Wiring Whiteboard ==")
        occ("config:app:set", "whiteboard", "collabBackendUrl", "--value", f"https://whiteboard.{domain}")
        occ("config:app:set", "whiteboard", "jwt_secret_key", "--value", whiteboard_env["JWT_SECRET_KEY"])
    else:
        print("== Skipping Whiteboard wiring (services/whiteboard/.env not set up) ==")

    if (REPO_ROOT / "services" / "clamav").is_dir():
        print("== Wiring files_antivirus (daemon mode, ClamAV) ==")
        occ("app:enable", "files_antivirus", check=False)
        occ("config:app:set", "files_antivirus", "av_mode", "--value", "daemon")
        occ("config:app:set", "files_antivirus", "av_host", "--value", "clamav")
        occ("config:app:set", "files_antivirus", "av_port", "--value", "3310")
        occ("config:app:set", "files_antivirus", "av_infected_action", "--value", "only_log")
        occ("config:app:set", "files_antivirus", "av_stream_max_length", "--value", "104857600")
    else:
        print("== Skipping files_antivirus wiring (services/clamav/ not set up) ==")

    print("== Removing enterprise/business-bundle apps ==")
    for app in APPS_TO_REMOVE:
        occ("app:remove", app, check=False)

    print("== Disabling shipped/core apps that can't be removed ==")
    for app in sorted(SHIPPED_CANNOT_DISABLE):
        occ("app:disable", app, check=False)

    print("== Disabling the global lookup directory (privacy) ==")
    occ("config:system:set", "lookup_server", "--value", "")

    print("\nDone. `docker exec -u www-data nextcloud php occ app:list` to review the final state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
