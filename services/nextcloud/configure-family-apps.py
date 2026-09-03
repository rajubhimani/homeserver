#!/usr/bin/env python3
"""Configure Nextcloud for family Drive/Calendar/Talk use on a fresh install.

Usage: uv run services/nextcloud/configure-family-apps.py   (from repo root)
       uv run services/nextcloud/configure-family-apps.py --yes    (skip the confirmation prompt)
       uv run services/nextcloud/configure-family-apps.py --list   (just report what's installed, no action taken)

Installs and enables the apps a family actually uses (Files, Calendar,
Contacts, Talk, Mail, Deck, Whiteboard, Office/ONLYOFFICE) and wires up
ONLYOFFICE/Whiteboard/ClamAV integration from their own .env files if those
services are set up -- unconditionally, no prompt, since that's unambiguous
setup work.

Then shows the full list of enterprise/business-bundle apps it would
disable/remove (workflow automation, retention policies, LDAP/SAML,
social-media sharing, the global lookup directory, etc. -- see
docs/services/nextcloud.md for the reasoning per app) and asks for
confirmation before touching any of them. Answer no (or run non-interactively
without --yes) and that whole step is skipped -- everything else still runs.

Safe to re-run any time (idempotent -- every occ command here is itself
idempotent: install-if-missing, enable-if-disabled, disable-if-enabled).

Requires Nextcloud to already be past its own first-run install (this
script only runs `occ` commands, which need a working install). Bring it
up and finish the setup wizard / initial admin login first if this is a
truly fresh instance, then run this.

Background/rationale for each decision: docs/services/nextcloud.md
"""

from __future__ import annotations

import argparse
import json
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

# Enterprise/business-bundle apps that add nothing for personal/family use,
# with the one-line reason shown at the confirmation prompt. Full background
# per app: docs/services/nextcloud.md's "Enterprise app cleanup" section.
APPS_TO_REMOVE: dict[str, str] = {
    "terms_of_service": "Enterprise ToS-acceptance onboarding flow",
    "support": '"Buy Nextcloud GmbH enterprise support" upsell app',
    "socialsharing_diaspora": "Social-media share button on files (Diaspora)",
    "socialsharing_facebook": "Social-media share button on files (Facebook)",
    "socialsharing_twitter": "Social-media share button on files (Twitter/X)",
    "socialsharing_email": "Social-media-style share-by-email button on files",
    "survey_client": "Sends anonymous usage telemetry back to Nextcloud",
    "files_confidential": 'Enterprise "mark file confidential" compliance tagging',
    "files_retention": "Auto-deletes files per a retention policy -- real data-loss risk if ever configured",
    "files_automatedtagging": "Workflow-rule-based auto-tagging (business automation)",
    "files_downloadlimit": "Caps download counts on share links (business use case, e.g. limiting client access)",
    "user_ldap": "Enterprise LDAP SSO backend -- unused in this stack",
    "user_saml": "Enterprise SAML SSO backend -- unused in this stack",
    "webhook_listeners": "Lets other apps register webhooks off Nextcloud events (dev/automation feature)",
    "nextcloud_announcements": "Official Nextcloud marketing broadcasts (not local admin announcements)",
    "groupfolders": "Team/org shared-folder permissions -- more than family sharing needs",
    "circles": "Advanced team/community sharing groups",
    "tables": "Mini spreadsheet/database app",
    "forms": "Survey/form builder",
    "collectives": "Team wiki pages",
    "related_resources": "Cross-app related-resource suggestions tied to federation/teams",
    "integration_forgejo_gitea": "Forgejo notification/link-preview integration -- personal dev convenience, not a family feature",
}

# Nextcloud won't let these be disabled OR removed (shipped/core) -- they stay
# enabled no matter what. Harmless: inert with no rules/config using them once
# the apps that would configure them (files_retention, files_automatedtagging,
# etc.) are gone. The disable attempt is still made, purely so the failure
# shows up in the output rather than looking silently skipped.
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


def confirm_cleanup(auto_yes: bool) -> bool:
    print("\nThe following apps are enterprise/business-bundle features with no")
    print("value for personal/family use. They'll be disabled (and removed where")
    print("Nextcloud allows it), plus the global lookup directory turned off:\n")
    for app, reason in APPS_TO_REMOVE.items():
        print(f"  - {app}: {reason}")
    print(f"  - (shipped/core, will stay enabled -- Nextcloud won't allow disabling these) {', '.join(sorted(SHIPPED_CANNOT_DISABLE))}")
    print("  - config: lookup_server set empty (stops publishing profile fields to")
    print("    Nextcloud's global public user directory)")

    if auto_yes:
        print("\n--yes passed, proceeding without prompting.")
        return True
    if not sys.stdin.isatty():
        print("\nNot running interactively and --yes wasn't passed -- skipping this step.")
        return False
    answer = input("\nDisable/remove these now? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def get_app_states() -> dict[str, str]:
    """Returns {app_id: 'enabled'|'disabled'|'not installed'} from live occ app:list."""
    result = subprocess.run(
        ["docker", "exec", "-u", "www-data", "nextcloud", "php", "occ", "app:list", "--output=json"],
        capture_output=True, text=True,
    )
    states: dict[str, str] = {}
    if result.returncode != 0:
        return states
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return states
    for app_id in data.get("enabled", {}):
        states[app_id] = "enabled"
    for app_id in data.get("disabled", {}):
        states[app_id] = "disabled"
    return states


def list_installed_apps() -> None:
    """Pure read-only report -- what's actually installed right now, grouped
    into the same categories the rest of this script reasons about, plus
    anything neither list knows about ('Other / core'). Takes no action."""
    states = get_app_states()
    known = set(FAMILY_APPS) | set(APPS_TO_REMOVE) | SHIPPED_CANNOT_DISABLE

    print("Family apps:")
    for app in FAMILY_APPS:
        if app in states:
            print(f"  [{states[app]:^10}] {app}")

    print("\nEnterprise/business-bundle apps (candidates for the cleanup step):")
    for app in list(APPS_TO_REMOVE) + sorted(SHIPPED_CANNOT_DISABLE):
        if app in states:
            reason = APPS_TO_REMOVE.get(app, "shipped/core, can't be disabled or removed")
            print(f"  [{states[app]:^10}] {app} -- {reason}")

    other_enabled = sorted(a for a, s in states.items() if s == "enabled" and a not in known)
    other_disabled = sorted(a for a, s in states.items() if s == "disabled" and a not in known)
    print(f"\nOther (core/uncategorized) apps: {len(other_enabled)} enabled, {len(other_disabled)} disabled")
    if other_enabled:
        print("  Enabled:  " + ", ".join(other_enabled))
    if other_disabled:
        print("  Disabled: " + ", ".join(other_disabled))


def print_final_picture(cleanup_applied: bool) -> None:
    print("\n" + "=" * 60)
    print("FINAL PICTURE")
    print("=" * 60)

    states = get_app_states()

    print("\nFamily apps:")
    for app in FAMILY_APPS:
        print(f"  [{states.get(app, 'not installed'):^12}] {app}")

    print("\nEnterprise/business-bundle apps:")
    if cleanup_applied:
        for app in APPS_TO_REMOVE:
            print(f"  [{states.get(app, 'removed'):^12}] {app}")
        for app in sorted(SHIPPED_CANNOT_DISABLE):
            print(f"  [{states.get(app, 'enabled'):^12}] {app}  (shipped/core -- Nextcloud won't let this be disabled or removed; stays enabled but inert, no config/rules use it)")
        print("\n  lookup_server: cleared (not publishing to the global directory)")
    else:
        print("  Cleanup was skipped -- still in whatever state they were in before this run:")
        for app in APPS_TO_REMOVE:
            print(f"  [{states.get(app, 'not installed'):^12}] {app}")
        print("\n  Run this script again and answer yes (or pass --yes) to apply the cleanup.")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes", "-y", action="store_true",
        help="Skip the confirmation prompt and proceed with the enterprise-app cleanup.",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="Just print what's currently installed, grouped by category. Takes no action.",
    )
    args = parser.parse_args()

    require_nextcloud_installed()

    if args.list:
        list_installed_apps()
        return 0

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

    cleanup_applied = confirm_cleanup(args.yes)
    if cleanup_applied:
        print("\n== Removing enterprise/business-bundle apps ==")
        for app in APPS_TO_REMOVE:
            occ("app:remove", app, check=False)

        print("== Attempting to disable shipped/core apps (expected to fail, kept for visibility) ==")
        for app in sorted(SHIPPED_CANNOT_DISABLE):
            occ("app:disable", app, check=False)

        print("== Disabling the global lookup directory (privacy) ==")
        occ("config:system:set", "lookup_server", "--value", "")
    else:
        print("\nSkipped -- leaving the enterprise/business-bundle apps as they are.")
        print("Re-run this script any time (or answer yes) to apply that cleanup later.")

    print_final_picture(cleanup_applied)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
