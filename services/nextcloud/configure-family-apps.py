#!/usr/bin/env python3
"""Configure Nextcloud for family Drive/Calendar/Talk use on a fresh install.

Usage: uv run services/nextcloud/configure-family-apps.py    (from repo root)
       uv run services/nextcloud/configure-family-apps.py --yes     (skip prompts, apply a saved selection if one exists, else the full list)
       uv run services/nextcloud/configure-family-apps.py --fresh   (ignore any saved selection, decide from scratch)
       uv run services/nextcloud/configure-family-apps.py --list    (just report what's installed, no action taken)

Installs and enables the apps a family actually uses (Files, Calendar,
Contacts, Talk, Mail, Deck, Whiteboard, Office/ONLYOFFICE) and wires up
ONLYOFFICE/Whiteboard/ClamAV integration from their own .env files if those
services are set up -- unconditionally, no prompt, since that's unambiguous
setup work.

Then walks through the enterprise/business-bundle apps that add nothing for
personal use (workflow automation, retention policies, LDAP/SAML,
social-media sharing, the global lookup directory, etc. -- see
docs/services/nextcloud.md for the reasoning per app). At the confirmation
step you choose [a]ll at once, [o]ne app at a time (keep-or-remove each),
or [n]o/skip entirely -- and can save whatever you decided to
family-apps-selection.json (gitignored, local to this install) so a later
run reuses it instead of re-asking. A saved selection is applied
automatically on --yes or non-interactive runs (no TTY) -- pass --fresh to
ignore it and decide from scratch instead.

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
from datetime import datetime, timezone
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVICE_DIR.parent.parent
SELECTION_FILE = SERVICE_DIR / "family-apps-selection.json"

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


def load_saved_selection() -> tuple[dict[str, str], str] | None:
    """Returns (selection, saved_at) or None if no valid saved file exists.

    Apps in today's APPS_TO_REMOVE that aren't in the saved file (added to
    the script after the file was last saved) default to "keep" -- never
    silently start removing something the user was never actually asked
    about."""
    if not SELECTION_FILE.exists():
        return None
    try:
        data = json.loads(SELECTION_FILE.read_text())
        raw_selection = data["selection"]
        saved_at = data["saved_at"]
    except (json.JSONDecodeError, KeyError, OSError):
        return None
    selection = {app: raw_selection.get(app, "keep") for app in APPS_TO_REMOVE}
    return selection, saved_at


def save_selection(selection: dict[str, str]) -> None:
    SELECTION_FILE.write_text(json.dumps(
        {"saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "selection": selection},
        indent=2,
    ) + "\n")
    print(f"  Saved to {SELECTION_FILE.relative_to(REPO_ROOT)}")


def prompt_mode() -> str:
    while True:
        answer = input("\nApply how? [a]ll at once / [o]ne by one / [n]o, skip: ").strip().lower()
        if answer in ("a", "all"):
            return "a"
        if answer in ("o", "one"):
            return "o"
        if answer in ("n", "no", ""):
            return "n"
        print("  Please answer a, o, or n.")


def run_one_by_one() -> dict[str, str]:
    print()
    selection: dict[str, str] = {}
    for app, reason in APPS_TO_REMOVE.items():
        answer = input(f"  {app} -- {reason}\n    Remove? [y/N]: ").strip().lower()
        selection[app] = "remove" if answer in ("y", "yes") else "keep"
    return selection


def apply_selection(selection: dict[str, str]) -> None:
    to_remove = [app for app, decision in selection.items() if decision == "remove"]
    print(f"\n== Removing {len(to_remove)} enterprise/business-bundle app(s) ==")
    for app in to_remove:
        occ("app:remove", app, check=False)

    print("== Attempting to disable shipped/core apps (expected to fail, kept for visibility) ==")
    for app in sorted(SHIPPED_CANNOT_DISABLE):
        occ("app:disable", app, check=False)

    print("== Disabling the global lookup directory (privacy) ==")
    occ("config:system:set", "lookup_server", "--value", "")


def confirm_cleanup(auto_yes: bool, fresh: bool) -> dict[str, str] | None:
    print("\nThe following apps are enterprise/business-bundle features with no")
    print("value for personal/family use. They can be disabled (and removed where")
    print("Nextcloud allows it), plus the global lookup directory turned off:\n")
    for app, reason in APPS_TO_REMOVE.items():
        print(f"  - {app}: {reason}")
    print(f"  - (shipped/core, will stay enabled -- Nextcloud won't allow disabling these) {', '.join(sorted(SHIPPED_CANNOT_DISABLE))}")
    print("  - config: lookup_server set empty (stops publishing profile fields to")
    print("    Nextcloud's global public user directory)")

    saved = None if fresh else load_saved_selection()

    non_interactive = auto_yes or not sys.stdin.isatty()
    if non_interactive:
        if saved:
            selection, saved_at = saved
            reason = "--yes passed" if auto_yes else "not running interactively"
            print(f"\n{reason} -- a saved selection exists (from {saved_at}), applying it.")
            return selection
        if auto_yes:
            print("\n--yes passed, no saved selection -- proceeding with the full list.")
            return {app: "remove" for app in APPS_TO_REMOVE}
        print("\nNot running interactively, --yes wasn't passed, and no saved selection exists -- skipping this step.")
        return None

    if saved:
        selection, saved_at = saved
        n_remove = sum(1 for d in selection.values() if d == "remove")
        n_keep = len(selection) - n_remove
        print(f"\nFound a saved selection from {saved_at}: {n_remove} to remove, {n_keep} to keep.")
        answer = input("Reuse it, or start fresh? [r]euse / [f]resh: ").strip().lower()
        if answer in ("r", "reuse"):
            return selection

    mode = prompt_mode()
    if mode == "n":
        return None
    selection = {app: "remove" for app in APPS_TO_REMOVE} if mode == "a" else run_one_by_one()

    answer = input("\nSave this selection for next time? [y/N]: ").strip().lower()
    if answer in ("y", "yes"):
        save_selection(selection)

    return selection


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
    saved = load_saved_selection()

    print("Family apps:")
    for app in FAMILY_APPS:
        if app in states:
            print(f"  [{states[app]:^10}] {app}")

    print("\nEnterprise/business-bundle apps (candidates for the cleanup step):")
    if saved:
        print(f"  (saved selection from {saved[1]} shown below)")
    for app in list(APPS_TO_REMOVE) + sorted(SHIPPED_CANNOT_DISABLE):
        if app not in states:
            continue
        reason = APPS_TO_REMOVE.get(app, "shipped/core, can't be disabled or removed")
        tag = f" (saved: {saved[0][app]})" if saved and app in saved[0] else ""
        print(f"  [{states[app]:^10}] {app} -- {reason}{tag}")

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
        help="Skip prompts: apply a saved selection if one exists, otherwise the full cleanup list.",
    )
    parser.add_argument(
        "--fresh", action="store_true",
        help="Ignore any saved selection and decide from scratch.",
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

    selection = confirm_cleanup(args.yes, args.fresh)
    cleanup_applied = selection is not None
    if cleanup_applied:
        apply_selection(selection)
    else:
        print("\nSkipped -- leaving the enterprise/business-bundle apps as they are.")
        print("Re-run this script any time (or answer yes) to apply that cleanup later.")

    print_final_picture(cleanup_applied)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
