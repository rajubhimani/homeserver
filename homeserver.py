#!/usr/bin/env python3
"""homeserver.py — manage all homeserver services (Python port of homeserver.sh)

Usage:
  python homeserver.py <env> <up|down|restart|logs|update|backup|restore|snapshots|reset> <min|core|daily|browser|office|automation-ai|extra|all|running|group:<name>|service...> [--profile <name>] [--no-backup] [--no-ml] [--no-wg] [--fresh] [--snapshot <ts>] [--yes]

  Any command targeting a tier keyword (min/core/daily/browser/office/automation-ai/extra/all/running),
  'group:<name>', or a bare bundle name (e.g. 'browser') prints the exact
  resolved service list and asks for confirmation before acting — pass
  --yes/-y to skip the prompt (e.g. non-interactive/cron use). Naming
  explicit service(s) directly (e.g. 'up nextcloud vaultwarden') never
  prompts — you already said exactly what you want.
  Exception: 'reset' always asks (type 'reset'), even for named services,
  and refuses outright when stdin isn't a terminal unless --yes is given.
  python homeserver.py <env> -r <service...>   (shorthand for restart)
  python homeserver.py <env> up group:notes    start every service in category/subcategory
                                                'notes' (or any other group — see services.json's
                                                'category'/'subcategory' fields for valid names).
                                                Works with every action, same as min/core/all.
  python homeserver.py <env> precreate <min|core|all|service...> [--update]
                                                create containers without starting them, so a
                                                never-started service shows up as a stack in
                                                Portainer (auto-detected by its labels) and can be
                                                started from there later — skips anything that
                                                already has containers. Manual-tier services aren't
                                                included in 'all' here either — list them by name
                                                alongside 'all' if you want them too.
                                                --update: force-recreate containers that already
                                                exist (e.g. after an .env/compose edit) instead of
                                                skipping them — still refuses to touch a service
                                                that's currently running (use 'up' for that).
  python homeserver.py gc [--yes]              reclaim Docker disk space (prune + Windows VHDX compaction)
  python homeserver.py orphaned-volumes [service|all] [--yes]
                                                list/remove volumes not declared in a service's current compose.yml
  python homeserver.py status (or ps)          list every known service, tier by tier, marking which are running,
                                                plus every group and exactly which services 'group:<name>' resolves to
  python homeserver.py fix-network [--yes]     detect + recreate any running container left detached from the
                                                'homeserver' network (looks running/healthy but unreachable by
                                                everything else — a plain restart does not fix this)

Service tiers:
  min    — bare minimum to run the server (beszel, cloudflared, nginx-plain, landing, docs, portainer)
  core   — full default stack, includes min. 'up core' bootstraps any of min
           NOT already running (idempotent otherwise); 'down core' stops
           ONLY core, min is left running — 'down all' is the only command
           that also stops min.
  daily  — apps used regularly but not core infra; opt-in, NOT included by
           'up core'. 'up daily' bootstraps any of min/core NOT already
           running, then starts daily; 'down daily' stops ONLY daily, min/core
           are left running. You flip this tier on/off yourself as needed.
  browser — the Browser Hub's remote browsers (firefox, chromium, brave,
           mullvad-browser, librewolf, zen, helium, chrome, edge, vivaldi);
           opt-in, same idiom as daily but bootstraps min/core/daily first.
           'browser' is the tier keyword — it takes precedence over the
           same-named bundle; use 'group:browser' to act on just the
           browsers without the lower-tier cascade (e.g. restart/update).
  office — firm/business apps (calcom, listmonk, plane, vikunja, appflowy,
           stirling-pdf-lite, stirling-pdf); opt-in, same idiom as daily but
           bootstraps min/core/daily/browser first.
  automation-ai — workflow/automation/AI apps (ollama, open-webui, n8n,
           airflow, temporal, dagster); opt-in, bootstraps
           min/core/daily/browser/office first.
  extra  — everything else, opt-in (observability, paperless, erpnext, ...);
           bootstraps min/core/daily/browser/office/automation-ai first.
  all    — core + daily + browser + office + automation-ai + extra (everything)

  Every `down` target (a service, group, tier, or all) also stops containers
  from every optional Compose profile declared by the selected service.
  extra  — optional services, started with 'up all' or individually
  manual — never auto-started by any tier (VPN services, gitlab, stirling-pdf
           full) — start individually with 'up <service>'

IMPORTANT: When adding a new service —
  - Add to SERVICES_CORE if it should auto-start with 'up core'
  - Add to SERVICES_DAILY if it's used regularly but shouldn't auto-start
    with core — the user turns it on/off explicitly with 'up/down daily'
  - Add to SERVICES_BROWSER only if it's a Browser Hub member browser
  - Add to SERVICES_OFFICE/SERVICES_AUTOMATION_AI if it fits one of those
    opt-in groupings (firm/business apps, or workflow/automation/AI apps)
    instead of general-purpose daily
  - Add to SERVICES_EXTRA if it is optional/manual
  - Add to SERVICES_MANUAL if it duplicates another always-on service at much
    higher cost, or should only ever start deliberately (VPN)
  - That is all — 'up all' and 'down all' derive everything automatically

Backups: 'down' snapshots a service's named volumes + data dir into
service_data/backup/<service>/<timestamp>/ by default every time it stops —
pass --no-backup to skip. Snapshots beyond BACKUP_RETENTION (root .env,
default 5, -1 = unlimited) are auto-pruned, oldest first. 'restore' uses the
latest snapshot unless --snapshot <timestamp> is given; 'snapshots <service>'
lists what's available.

This is a pure functional port of homeserver.sh — same behavior, same CLI
shape. It exists to eliminate an entire class of bugs found running the
shell version through Git Bash/MSYS on Windows: MSYS auto-converts
POSIX-looking paths in both argv and environment variables before spawning
native Windows processes, which silently corrupted the DOCKER_SOCKET env var
and any docker exec/run argument containing a container-internal path (e.g.
/var/log/...). subprocess.run() with list-form args never goes through a
shell at all, so none of that applies here — no workarounds needed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from abc import ABC, abstractmethod
from pathlib import Path

# ── Paths & config ──────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
# Every service's own directory (compose.yml, .env, etc.) lives under
# services/<name>/, one level deeper than the repo root — keeps the root
# itself to just this script, service_data/, docker/, kubernetes/, and docs.
SERVICES_DIR = BASE_DIR / "services"
# service_data/data/<service>/  — live data, bind-mounted into containers
# service_data/backup/<service>/<YYYYMMDD-HHMMSS>/  — timestamped snapshots
# service_data/db_dump/<service>/<YYYYMMDD-HHMMSS>/  — logical Postgres dumps,
#   used by 'migrate' (e.g. Debian->Alpine image migration) — see 'dump'/'migrate'
# These stay directly under BASE_DIR, not SERVICES_DIR — service_data/ is a
# sibling of services/, not nested inside it.
SERVICE_DATA_ROOT = BASE_DIR / "service_data" / "data"
BACKUP_ROOT = BASE_DIR / "service_data" / "backup"
DB_DUMP_ROOT = BASE_DIR / "service_data" / "db_dump"


def load_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser — comments, blank lines, quoted values."""
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        result[key] = val
    return result


def load_services_json(path: Path) -> dict:
    """services.json is the single source of truth for both tier membership
    (this file) and landing-page grouping (services/landing/index.html,
    fetched at page load) — one entry per service instead of two hand-synced
    lists. See the homeserver-add-service skill for the schema. Called at
    module load time, before the colored-output helpers below exist yet —
    plain stderr on failure, not error()/warn()."""
    if not path.is_file():
        print(f"{path} not found — this repo can't run without it (services/tiers are defined there).", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


_ROOT_ENV = load_env_file(BASE_DIR / ".env")

DOMAIN = _ROOT_ENV.get("DOMAIN", "yourdomain.com")
RUNTIME = _ROOT_ENV.get("RUNTIME", "docker")
DOCKER_SOCKET = _ROOT_ENV.get("DOCKER_SOCKET", "/var/run/docker.sock")
# Snapshots to keep per service before auto-pruning the oldest; -1 = unlimited
BACKUP_RETENTION = int(_ROOT_ENV.get("BACKUP_RETENTION", "5"))
# reset-backup-<ts> folders (each reset's verified pre-wipe snapshot) to keep
# per service; they never count against BACKUP_RETENTION. -1 = unlimited.
RESET_BACKUP_RETENTION = int(_ROOT_ENV.get("RESET_BACKUP_RETENTION", "5"))
# 'subprocess' (default, zero extra deps) or 'python-on-whales' (optional —
# uv sync --extra docker-sdk) for typed exceptions/structured errors instead
# of parsed CLI text. Both call the same underlying docker/docker compose CLI
# — see DockerBackend below.
DOCKER_BACKEND_NAME = _ROOT_ENV.get("DOCKER_BACKEND", "subprocess")

# Only force DOCKER_HOST at the given socket path if it actually exists —
# true on native Linux and inside WSL with a Linux Docker/Podman daemon, but
# not on Windows: Docker Desktop for Windows has no /var/run/docker.sock
# outside a WSL distro, it uses its own named pipe. Skipping the override
# there lets docker/podman fall back to their default context.
os.environ["DOCKER_SOCKET"] = DOCKER_SOCKET
if os.path.exists(DOCKER_SOCKET):
    os.environ["DOCKER_HOST"] = f"unix://{DOCKER_SOCKET}"
    os.environ["CONTAINER_HOST"] = f"unix://{DOCKER_SOCKET}"

# ── Service tiers (additive: each tier builds on the previous) ─────
#
#   up min           = MIN
#   up core          = bootstrap any of MIN not already running, + CORE
#   up daily         = bootstrap any of MIN/CORE not already running, + DAILY
#                      (opt-in — never implied by 'up core')
#   up browser       = bootstrap any of MIN/CORE/DAILY not already running,
#                      + BROWSER (opt-in — never implied by 'up daily')
#   up office        = bootstrap any of MIN/CORE/DAILY/BROWSER not already
#                      running, + OFFICE (opt-in — never implied by 'up browser')
#   up automation-ai = bootstrap any of MIN/CORE/DAILY/BROWSER/OFFICE not already
#                      running, + AUTOMATION_AI (opt-in)
#   up extra         = bootstrap any of MIN/CORE/DAILY/BROWSER/OFFICE/AUTOMATION_AI
#                      not already running, + EXTRA (opt-in)
#   up all           = MIN + CORE + DAILY + BROWSER + OFFICE + AUTOMATION_AI + EXTRA,
#                      always (full cascade)
#
#   every down target  = selected services, reversed when tier/group/all;
#                        includes every Compose profile in each service
#
# 'up core'/'up daily' rely on do_up's own idempotency (plain `compose up -d`,
# no force_recreate) plus an explicit running-check (get_running_services())
# so an already-running lower tier is left untouched rather than re-listed —
# that running-check specifically avoids nginx-plain/landing's unconditional
# force-restart-on-every-up (see do_up) firing just because MIN was
# unconditionally bundled into the list.
#
# Derived from services.json (the single source of truth for tier membership
# AND landing-page grouping — see the homeserver-add-service skill) rather
# than hand-maintained here, so this file and the landing page can never
# drift out of sync with each other. Order is preserved from the JSON array,
# which is what actually matters (startup sequencing) — grouped by tier
# there for the same reason it was grouped here before.
#   - manual-only (SERVICES_MANUAL): never started by 'up min/core/all' (or
#     their down/restart/update/backup/restore equivalents) — start
#     individually with 'up <service>'. Currently gitlab/stirling-pdf,
#     each redundant with an always-on equivalent (forgejo,
#     stirling-pdf-lite) at meaningfully higher resource cost — see
#     each one's "tier" comment in services.json for specifics.

_SERVICES_DATA = load_services_json(BASE_DIR / "services.json")

# Landing-page entries can have a tier without being independently managed
# Compose stacks. For example, Firefly Importer is a card and container in
# Firefly's compose.yml, while Browser Hub is a virtual card for a bundle.
# Only entries with their own services/<slug>/ directory belong in lifecycle
# commands; the landing page still renders every entry from services.json.
def is_managed_service(entry: dict) -> bool:
    return bool(entry.get("tier")) and not entry.get("virtual") and (SERVICES_DIR / entry["slug"]).is_dir()


SERVICES_MIN = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "min" and is_managed_service(s)]
SERVICES_CORE = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "core" and is_managed_service(s)]
SERVICES_DAILY = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "daily" and is_managed_service(s)]
SERVICES_BROWSER = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "browser" and is_managed_service(s)]
SERVICES_OFFICE = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "office" and is_managed_service(s)]
SERVICES_AUTOMATION_AI = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "automation-ai" and is_managed_service(s)]
SERVICES_EXTRA = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "extra" and is_managed_service(s)]
SERVICES_MANUAL = [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == "manual" and is_managed_service(s)]

# category/subcategory -> ordered list of slugs, e.g. SERVICE_GROUPS["notes"]
# or SERVICE_GROUPS["productivity"] — powers 'up group:<name>' (and every
# other tier-aware action) the same way SERVICES_MIN/CORE/EXTRA do. Only
# entries with an independent tier are groupable — a group is something you
# can start/stop, and firefly-importer (no tier, rides along with firefly)
# isn't independently startable.
SERVICE_GROUPS: dict[str, list[str]] = {}
# category -> its subcategories (sorted), e.g. CATEGORY_SUBGROUPS["dev"] ==
# ["automation", "git", "identity", "tools"] — only dev/productivity split
# further; storage/system have no subcategory, so they're already the
# smallest group for those areas. Purely for 'status'/'ps' to render the
# category/subcategory nesting instead of one flat list.
CATEGORY_SUBGROUPS: dict[str, set[str]] = {}
for _s in _SERVICES_DATA["services"]:
    # Exclude landing-only cards too: group/status membership must contain
    # only independently startable services.
    if not is_managed_service(_s):
        continue
    for _key in ("category", "subcategory"):
        _val = _s.get(_key)
        if _val:
            SERVICE_GROUPS.setdefault(_val, []).append(_s["slug"])
    _cat, _sub = _s.get("category"), _s.get("subcategory")
    if _cat and _sub:
        CATEGORY_SUBGROUPS.setdefault(_cat, set()).add(_sub)
del _s, _key, _val, _cat, _sub

# "bundle" groups multiple independently-deployed service directories under
# one startable name — a hub-of-containers (Browser Hub's ten browser
# containers behind one shared login, see docs/services/browser-hub.md) that
# isn't a category/subcategory grouping. A member declares "bundle": "<hub
# slug>"; the hub's own (virtual) entry can declare "requires": [...] for
# extra infra it needs that isn't itself a member (nginx-plain, in that
# example). Fully data-driven — a future bundle needs zero changes here, just
# "bundle"/"requires" fields in services.json. BUNDLE_MEMBERS' keys double as
# the set of bare tokens ('up <bundle>', not 'up group:<bundle>') the CLI
# expands — see the bare-token handling below.
#
# "requires" is deliberately kept OUT of SERVICE_GROUPS/BUNDLE_MEMBERS and
# only spliced in for up-family actions (see the action check below) — never
# for down/restart/update/backup/restore/dump. nginx-plain is exactly why:
# it's shared infra for the WHOLE stack, not something 'browser' owns, so
# 'down browser' must never stop it just because 'up browser' needs it
# running. (Confirmed real incident: this bug shipped once and 'down
# browser' took nginx-plain down with it, before this split existed.)
BUNDLE_MEMBERS: dict[str, list[str]] = {}
BUNDLE_REQUIRES: dict[str, list[str]] = {}
for _s in _SERVICES_DATA["services"]:
    _bundle = _s.get("bundle")
    if _bundle:
        BUNDLE_MEMBERS.setdefault(_bundle, []).append(_s["slug"])
for _s in _SERVICES_DATA["services"]:
    if _s["slug"] in BUNDLE_MEMBERS:
        BUNDLE_REQUIRES[_s["slug"]] = _s.get("requires", [])
        SERVICE_GROUPS[_s["slug"]] = BUNDLE_MEMBERS[_s["slug"]]
del _s, _bundle

# nginx-plain and nginx (NPM) both bind to ports 80/443 — only one can run at
# a time. nginx-plain is the default (always in MIN). nginx (NPM) is
# manual-only — never auto-started by any tier. Starting either one
# automatically stops the other.
PROXY_STANDBY = "nginx"

# Timeout in seconds to wait for a service to become healthy
HEALTH_TIMEOUT = 180

# ── Output helpers ──────────────────────────────────────────────────

if sys.platform == "win32":
    # Enable ANSI/VT100 escape processing in legacy Windows consoles (no-op,
    # already on, in Windows Terminal/PowerShell 7/Git Bash). subprocess
    # (not os.system, which is soft-deprecated) triggering a console app is
    # the standard trick for this — there's no direct WinAPI call exposed
    # via stdlib, so this side effect is the accepted way to do it.
    subprocess.run("", shell=True)
    # Windows Python defaults console stdout/stderr to the system codepage
    # (cp1252 typically), not UTF-8 — the em-dashes and status glyphs used
    # throughout this script's output (— ▶ ✔ ✖ ⚠ ━) silently corrupt into
    # "�" otherwise, even though the terminal itself supports UTF-8 fine.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def info(msg: str) -> None:
    print(f"{CYAN}▶ {msg}{RESET}")


def success(msg: str) -> None:
    print(f"{GREEN}✔ {msg}{RESET}")


def error(msg: str) -> None:
    print(f"{RED}✖ {msg}{RESET}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠ {msg}{RESET}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}\n")


# ── Docker backend abstraction ──────────────────────────────────────
#
# Two implementations of the same interface: SubprocessBackend (default, zero
# extra dependencies, calls `docker`/`docker compose` via subprocess and
# parses their text output) and PythonOnWhalesBackend (optional — pip package
# python-on-whales, itself still a wrapper around the same docker/docker
# compose CLI, but raises typed exceptions with structured .stderr/.return_code
# instead of leaving the caller to parse raw text). Select with DOCKER_BACKEND
# in the root .env. Everything above this line (do_up, do_down, etc.) talks
# only to the BACKEND instance, never to subprocess/docker directly.


def _healthcheck_seconds(hc: dict | None) -> dict:
    """Docker's .Config.Healthcheck (durations in ns, 0 = unset) -> seconds
    with Docker's documented defaults applied. {} when there's no check."""
    if not hc or not hc.get("Test") or hc["Test"][0] == "NONE":
        return {}
    ns = 1_000_000_000
    return {
        "interval": (hc.get("Interval") or 30 * ns) / ns,
        "timeout": (hc.get("Timeout") or 30 * ns) / ns,
        "start_period": (hc.get("StartPeriod") or 0) / ns,
        "retries": hc.get("Retries") or 3,
    }


class DockerBackend(ABC):
    @abstractmethod
    def compose_up(
        self, files: list[Path], env: dict[str, str], profile: str | None,
        force_recreate: bool = False, exclude: list[str] | None = None, only: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Returns (success, combined stdout+stderr) — the caller inspects the
        text for port-conflict/Podman-quirk patterns regardless of backend.
        exclude: container names to scale to 0 (started normally otherwise) —
        e.g. immich-ml's --no-ml, see do_up. only: start just these container
        names instead of the whole project — e.g. do_migrate standing up a
        fresh <service>-db alone before the app container touches it."""

    @abstractmethod
    def db_pg_dump(self, container: str, user: str, db: str) -> tuple[bool, bytes, str]:
        """Runs pg_dump -F c (custom format) inside container, captured directly
        via subprocess rather than writing to a container-internal path — see
        do_dump for why (Windows/Git-Bash MSYS path-mangling on POSIX-looking
        container paths). Returns (success, dump_bytes, stderr_text)."""

    @abstractmethod
    def db_pg_restore(self, container: str, user: str, db: str, dump: bytes) -> tuple[bool, str]:
        """Streams dump_bytes into pg_restore inside container. Returns
        (success, stderr_text)."""

    @abstractmethod
    def db_pg_dumpall_roles(self, container: str, user: str) -> tuple[bool, bytes, str]:
        """Runs pg_dumpall --roles-only inside container — captures CREATE
        ROLE definitions (with passwords), which a per-database pg_dump never
        does since roles are cluster-wide, not database-scoped. Returns
        (success, sql_bytes, stderr_text)."""

    @abstractmethod
    def db_psql_apply(self, container: str, user: str, db: str, sql: bytes) -> tuple[bool, str]:
        """Streams plain SQL into psql inside container (no ON_ERROR_STOP —
        used for the roles dump above, where 'role already exists' for
        roles the fresh cluster's own initdb already created is expected
        and harmless). Returns (success, stderr_text)."""

    @abstractmethod
    def db_exec(
        self, container: str, cmd: list[str], input: bytes | None = None, env: dict[str, str] | None = None,
    ) -> tuple[bool, bytes, str]:
        """docker exec [-i] [-e K=V ...] container cmd..., stdin from input,
        stdout captured as bytes. The shared-db helpers (provision_shared_db,
        shared-db dump/restore) build psql/mariadb/mariadb-dump commands on
        top of this; env carries credentials (e.g. MYSQL_PWD) so they never
        appear in the process list. Returns (success, stdout_bytes,
        stderr_text)."""

    @abstractmethod
    def compose_create(
        self, files: list[Path], env: dict[str, str], profile: str | None, force_recreate: bool = False,
    ) -> tuple[bool, str]:
        """docker compose create — makes containers (pulls images, wires
        networks/volumes) without starting them. Used by 'precreate' so a
        service becomes visible/startable from Portainer's own UI without
        actually running it yet. force_recreate: used by 'precreate --update'
        to rebuild containers that already exist (e.g. after an .env change)
        instead of leaving their stale config in place. Returns (success,
        combined output)."""

    @abstractmethod
    def compose_down(self, files: list[Path], env: dict[str, str], profile: str | None) -> bool: ...

    @abstractmethod
    def compose_pull(self, files: list[Path], env: dict[str, str]) -> bool: ...

    @abstractmethod
    def compose_logs_follow(self, files: list[Path], env: dict[str, str]) -> None: ...

    @abstractmethod
    def running_container_names(self) -> list[str]: ...

    @abstractmethod
    def all_container_names(self) -> list[str]: ...

    @abstractmethod
    def container_status(self, name: str) -> str | None:
        """'running', 'exited', 'dead', 'created', etc. — None if not found."""

    @abstractmethod
    def container_health(self, name: str) -> str:
        """'healthy', 'unhealthy', 'starting', or 'none' (no HEALTHCHECK defined)."""

    @abstractmethod
    def container_healthcheck(self, name: str) -> dict:
        """The container's effective healthcheck settings in seconds:
        {"interval", "timeout", "start_period", "retries"} — from compose or
        the image's own HEALTHCHECK, with Docker's defaults (30s/30s/0s/3)
        where unset. {} if the container has no healthcheck or doesn't exist.
        wait_healthy uses it to wait as long as Docker itself would before
        calling a container unhealthy."""

    @abstractmethod
    def container_info(self, name: str) -> dict:
        """network_mode (HostConfig.NetworkMode), networks (list of network
        names currently in NetworkSettings.Networks — empty means the
        container has no live network endpoint, the detached/stale-network
        symptom this stack hit twice: a container created before the
        'homeserver' network was recreated during the 2026-09-04 IPv6-lockdown
        work kept running but could no longer be reached by anything else on
        it, see find_stale_network_containers), plus the compose labels
        needed to recreate it the same way it was originally started
        (compose_project, compose_service, config_files — a list of the
        compose file paths recorded on com.docker.compose.project.config_files).
        Returns {} if the container doesn't exist."""

    @abstractmethod
    def volumes_for_project(self, project: str) -> list[str]: ...

    @abstractmethod
    def volume_exists(self, name: str) -> bool: ...

    @abstractmethod
    def volume_create(self, name: str) -> None: ...

    @abstractmethod
    def volume_remove(self, name: str) -> bool: ...

    @abstractmethod
    def network_exists(self, name: str) -> bool: ...

    @abstractmethod
    def network_create(self, name: str, subnet: str | None = None) -> None: ...

    @abstractmethod
    def network_subnets(self, name: str) -> list[str]:
        """The subnets of an existing network ([] if it has none or doesn't exist)."""

    @abstractmethod
    def tar_volume_to(self, volume: str, dest_dir: Path, archive_name: str) -> bool:
        """Tar a named volume's contents into dest_dir/archive_name via a throwaway container."""

    @abstractmethod
    def tar_dir_to(self, host_dir: Path, dest_dir: Path, archive_name: str) -> bool: ...

    @abstractmethod
    def untar_into_volume(self, volume: str, archive_path: Path) -> bool:
        """Clear the volume (if it has contents) and extract archive_path into it."""

    @abstractmethod
    def untar_into_dir(self, archive_path: Path, dest_dir: Path) -> bool:
        """Clear dest_dir (if it has contents) and extract archive_path into
        it -- same contract as untar_into_volume. Restoring an older snapshot
        must always leave dest_dir as an exact copy of the snapshot, never a
        merge with whatever was already there: for a WAL-based store
        (Prometheus, Loki) a merge produces a directory holding segments from
        two different points in the WAL's history, which the engine reads as
        corruption ("segments are not sequential") rather than just stale
        data. Confirmed as the root cause of a real incident against this
        stack's own observability service data."""

    @abstractmethod
    def archive_paths(self, mounts: dict[Path, str], members: list[str], excludes: list[str], dest_file: Path) -> tuple[bool, str]:
        """tar+gzip `members` (paths relative to /src inside a throwaway root
        container, where each mounts[host_path] is bind-mounted read-only at
        /src/<name>) into dest_file. Root so container-owned files (root, or
        an app's own uid) are readable — a host-user tar would silently skip
        them. excludes are tar --exclude patterns. Used by `archive`.
        Returns (success, stderr_text)."""

    @abstractmethod
    def remove_dir(self, host_dir: Path) -> bool:
        """Delete host_dir entirely through a throwaway container running as
        root. Containers create files under service_data/data/<service> as
        root or their own uid, so a plain shutil.rmtree from homeserver.py
        (running as the host user) fails with Permission denied — the bug
        that broke the first 'reset' run on 2026-10-02. Mounts the parent and
        removes the child, so the directory itself goes too."""

    @abstractmethod
    def system_prune(self) -> tuple[bool, str]:
        """docker system prune -a --volumes -f — removes every unused image,
        stopped container, and unnamed/anonymous volume on the whole Docker
        host, not just this stack. Returns (success, combined output)."""

    @abstractmethod
    def builder_prune(self) -> tuple[bool, str]:
        """docker builder prune -a -f — clears the build cache. Returns
        (success, combined output)."""


class SubprocessBackend(DockerBackend):
    def _run(self, args: list[str], env: dict[str, str] | None = None, capture: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            [RUNTIME] + args, env=env,
            capture_output=capture, text=True if capture else None,
        )

    def _compose_args(self, files: list[Path], profile: str | None) -> list[str]:
        args = ["compose"]
        for f in files:
            args += ["-f", str(f)]
        if profile:
            args += ["--profile", profile]
        return args

    def compose_up(self, files, env, profile, force_recreate=False, exclude=None, only=None):
        args = self._compose_args(files, profile) + ["up", "-d"]
        if force_recreate:
            args.append("--force-recreate")
        for name in exclude or []:
            args += ["--scale", f"{name}=0"]
        if only:
            args += list(only)
        proc = self._run(args, env=env)
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")

    def db_pg_dump(self, container, user, db):
        # Bytes mode (not _run's text=True) — custom-format dumps are binary.
        proc = subprocess.run(
            [RUNTIME, "exec", container, "pg_dump", "-U", user, "-d", db, "-F", "c"],
            capture_output=True,
        )
        return proc.returncode == 0, proc.stdout, (proc.stderr or b"").decode(errors="replace")

    def db_pg_restore(self, container, user, db, dump):
        # --clean --if-exists: the target is always a container we just
        # created for this migration, so drop-then-recreate is safe even
        # when the image's own docker-entrypoint-initdb.d/ already bootstrapped
        # a schema (e.g. guacamole's 01-schema.sql) before the restore runs.
        # --no-owner only (deliberately NOT --no-privileges): the dump's
        # captured GRANT statements are exactly what a secondary role (e.g.
        # Nextcloud's own ad-hoc 'oc_admin', not the connecting POSTGRES_USER)
        # needs on these objects — stripping them left oc_admin able to log
        # in (roles dump/apply handles that) but with zero table privileges.
        # This only works because roles are applied *before* this restore
        # runs (see do_migrate) — do that first or these GRANTs fail on a
        # role that doesn't exist yet.
        proc = subprocess.run(
            [
                RUNTIME, "exec", "-i", container, "pg_restore", "-U", user, "-d", db,
                "--no-owner", "--clean", "--if-exists",
            ],
            input=dump, capture_output=True,
        )
        return proc.returncode == 0, (proc.stderr or b"").decode(errors="replace")

    def db_pg_dumpall_roles(self, container, user):
        proc = subprocess.run(
            [RUNTIME, "exec", container, "pg_dumpall", "-U", user, "--roles-only"],
            capture_output=True,
        )
        return proc.returncode == 0, proc.stdout, (proc.stderr or b"").decode(errors="replace")

    def db_psql_apply(self, container, user, db, sql):
        # No ON_ERROR_STOP: 'role already exists' for roles the fresh
        # cluster's own initdb/POSTGRES_USER already created is expected —
        # psql skips the failing statement and keeps applying the rest.
        proc = subprocess.run(
            [RUNTIME, "exec", "-i", container, "psql", "-U", user, "-d", db],
            input=sql, capture_output=True,
        )
        return proc.returncode == 0, (proc.stderr or b"").decode(errors="replace")

    def db_exec(self, container, cmd, input=None, env=None):
        args = [RUNTIME, "exec"]
        if input is not None:
            args.append("-i")
        # '-e NAME' (no '=value') makes docker copy the value from this
        # process's environment, so secrets never appear in the docker exec
        # argv on the host (visible to anyone running ps).
        run_env = None
        if env:
            run_env = {**os.environ, **env}
            for k in env:
                args += ["-e", k]
        proc = subprocess.run(args + [container] + list(cmd), input=input, capture_output=True, env=run_env)
        return proc.returncode == 0, proc.stdout, (proc.stderr or b"").decode(errors="replace")

    def compose_create(self, files, env, profile, force_recreate=False):
        args = self._compose_args(files, profile) + ["create"]
        if force_recreate:
            args.append("--force-recreate")
        proc = self._run(args, env=env)
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")

    def compose_down(self, files, env, profile):
        proc = self._run(self._compose_args(files, profile) + ["down"], env=env)
        return proc.returncode == 0

    def compose_pull(self, files, env):
        proc = self._run(self._compose_args(files, None) + ["pull"], env=env)
        return proc.returncode == 0

    def compose_logs_follow(self, files, env):
        subprocess.run([RUNTIME] + self._compose_args(files, None) + ["logs", "-f"], env=env)

    def running_container_names(self) -> list[str]:
        proc = self._run(["ps", "--format", "{{.Names}}"])
        return [n for n in proc.stdout.splitlines() if n]

    def all_container_names(self) -> list[str]:
        proc = self._run(["ps", "-a", "--format", "{{.Names}}"])
        return [n for n in proc.stdout.splitlines() if n]

    def container_status(self, name: str) -> str | None:
        proc = self._run(["inspect", "--format={{.State.Status}}", name])
        out = proc.stdout.strip()
        return out or None

    def container_health(self, name: str) -> str:
        proc = self._run(
            ["inspect", "--format={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", name]
        )
        return proc.stdout.strip() or "none"

    def container_healthcheck(self, name: str) -> dict:
        proc = self._run(["inspect", "--format={{json .Config.Healthcheck}}", name])
        try:
            hc = json.loads(proc.stdout.strip() or "null")
        except json.JSONDecodeError:
            return {}
        return _healthcheck_seconds(hc)

    def container_info(self, name: str) -> dict:
        fmt = (
            '{"network_mode":{{json .HostConfig.NetworkMode}},'
            '"networks":{{json .NetworkSettings.Networks}},'
            '"compose_project":{{json (index .Config.Labels "com.docker.compose.project")}},'
            '"compose_service":{{json (index .Config.Labels "com.docker.compose.service")}},'
            '"config_files":{{json (index .Config.Labels "com.docker.compose.project.config_files")}}}'
        )
        proc = self._run(["inspect", f"--format={fmt}", name])
        if proc.returncode != 0 or not proc.stdout.strip():
            return {}
        try:
            raw = json.loads(proc.stdout.strip())
        except json.JSONDecodeError:
            return {}
        config_files = raw.get("config_files") or ""
        return {
            "network_mode": raw.get("network_mode") or "",
            "networks": list((raw.get("networks") or {}).keys()),
            "compose_project": raw.get("compose_project") or "",
            "compose_service": raw.get("compose_service") or "",
            "config_files": config_files.split(",") if config_files else [],
        }

    def volumes_for_project(self, project: str) -> list[str]:
        # Match by Compose's own naming convention (<project>_<volume-name>)
        # rather than the com.docker.compose.project label — volumes created
        # manually (e.g. during a bind-mount-to-named-volume migration) never
        # get that label even after a real `compose up`, which silently
        # dropped them from backups. The naming convention is guaranteed
        # regardless of how the volume was created.
        proc = self._run(["volume", "ls", "-q"])
        prefix = f"{project}_"
        return [v for v in proc.stdout.splitlines() if v.startswith(prefix)]

    def volume_exists(self, name: str) -> bool:
        return self._run(["volume", "inspect", name]).returncode == 0

    def volume_create(self, name: str) -> None:
        self._run(["volume", "create", name])

    def volume_remove(self, name: str) -> bool:
        return self._run(["volume", "rm", name]).returncode == 0

    def network_exists(self, name: str) -> bool:
        return self._run(["network", "inspect", name]).returncode == 0

    def network_create(self, name: str, subnet: str | None = None) -> None:
        self._run(["network", "create"] + (["--subnet", subnet] if subnet else []) + [name])

    def network_subnets(self, name: str) -> list[str]:
        r = self._run(["network", "inspect", name, "--format", "{{range .IPAM.Config}}{{.Subnet}} {{end}}"])
        return r.stdout.split() if r.returncode == 0 else []

    def tar_volume_to(self, volume: str, dest_dir: Path, archive_name: str) -> bool:
        args = [
            "run", "--rm", "-v", f"{volume}:/from:ro", "-v", f"{dest_dir}:/backup", "alpine:3.21",
            "sh", "-c", f"tar czf /backup/{archive_name} -C /from .",
        ]
        return self._run(args).returncode == 0

    def tar_dir_to(self, host_dir: Path, dest_dir: Path, archive_name: str) -> bool:
        args = [
            "run", "--rm", "-v", f"{host_dir}:/from:ro", "-v", f"{dest_dir}:/backup", "alpine:3.21",
            "sh", "-c", f"tar czf /backup/{archive_name} -C /from .",
        ]
        return self._run(args).returncode == 0

    def untar_into_volume(self, volume: str, archive_path: Path) -> bool:
        args = [
            "run", "--rm", "-v", f"{volume}:/to", "-v", f"{archive_path.parent}:/backup", "alpine:3.21",
            "sh", "-c", f"find /to -mindepth 1 -delete; tar xzf /backup/{archive_path.name} -C /to",
        ]
        return self._run(args).returncode == 0

    def untar_into_dir(self, archive_path: Path, dest_dir: Path) -> bool:
        dest_dir.mkdir(parents=True, exist_ok=True)
        args = [
            "run", "--rm", "-v", f"{dest_dir}:/to", "-v", f"{archive_path.parent}:/backup", "alpine:3.21",
            "sh", "-c", f"find /to -mindepth 1 -delete; tar xzf /backup/{archive_path.name} -C /to",
        ]
        return self._run(args).returncode == 0

    def archive_paths(self, mounts, members, excludes, dest_file):
        # Raw subprocess in both backends: the member list goes in on stdin,
        # which python-on-whales' run() doesn't expose.
        args = [RUNTIME, "run", "--rm", "-i"]
        for host, name in mounts.items():
            args += ["-v", f"{Path(host).resolve()}:/src/{name}:ro"]
        args += ["-v", f"{dest_file.parent.resolve()}:/out", "alpine:3.21", "sh", "-c",
                 "cd /src && tar " + " ".join(f"--exclude='{e}'" for e in excludes)
                 + f" -cf - -T - | gzip -1 > '/out/{dest_file.name}'"]
        proc = subprocess.run(args, input="\n".join(members).encode(), capture_output=True)
        return proc.returncode == 0, (proc.stderr or b"").decode(errors="replace")

    def remove_dir(self, host_dir: Path) -> bool:
        host_dir = host_dir.resolve()
        if not host_dir.exists():
            return True
        args = ["run", "--rm", "-v", f"{host_dir.parent}:/parent", "alpine:3.21", "rm", "-rf", f"/parent/{host_dir.name}"]
        return self._run(args).returncode == 0 and not host_dir.exists()

    def system_prune(self) -> tuple[bool, str]:
        proc = self._run(["system", "prune", "-a", "--volumes", "-f"])
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")

    def builder_prune(self) -> tuple[bool, str]:
        proc = self._run(["builder", "prune", "-a", "-f"])
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


class PythonOnWhalesBackend(DockerBackend):
    """Same operations as SubprocessBackend, routed through python-on-whales
    for typed exceptions (DockerException: .stderr, .return_code,
    .docker_command) instead of parsed CLI text — still calls the same
    underlying docker/docker compose CLI under the hood."""

    def __init__(self):
        from python_on_whales import DockerClient  # noqa: PLC0415 (optional dep, imported lazily)
        self._DockerClient = DockerClient
        self._docker = DockerClient(client_type=RUNTIME if RUNTIME in ("docker", "podman") else "docker")

    def _client(self, files: list[Path] | None = None, profile: str | None = None):
        return self._DockerClient(
            client_type=RUNTIME if RUNTIME in ("docker", "podman") else "docker",
            compose_files=files or [],
            compose_profiles=[profile] if profile else [],
        )

    @staticmethod
    @contextlib.contextmanager
    def _env(env: dict[str, str] | None):
        if not env:
            yield
            return
        old = dict(os.environ)
        os.environ.clear()
        os.environ.update(env)
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(old)

    def compose_up(self, files, env, profile, force_recreate=False, exclude=None, only=None):
        from python_on_whales.exceptions import DockerException  # noqa: PLC0415
        client = self._client(files, profile)
        scales = {name: 0 for name in exclude} if exclude else None
        try:
            with self._env(env):
                client.compose.up(detach=True, force_recreate=force_recreate, wait=False, scales=scales, services=only)
            return True, ""
        except DockerException as e:
            out = f"{e.stderr or ''}\n{e.stdout or ''}"
            return False, out

    def db_pg_dump(self, container, user, db):
        # Raw subprocess rather than python-on-whales here — this backend's
        # main value (typed compose exceptions) doesn't apply to a plain
        # binary-stdio docker exec, and both backends ending up identical
        # for this one primitive is fine (see DockerBackend docstring).
        proc = subprocess.run(
            [RUNTIME, "exec", container, "pg_dump", "-U", user, "-d", db, "-F", "c"],
            capture_output=True,
        )
        return proc.returncode == 0, proc.stdout, (proc.stderr or b"").decode(errors="replace")

    def db_pg_restore(self, container, user, db, dump):
        # --clean --if-exists: the target is always a container we just
        # created for this migration, so drop-then-recreate is safe even
        # when the image's own docker-entrypoint-initdb.d/ already bootstrapped
        # a schema (e.g. guacamole's 01-schema.sql) before the restore runs.
        # --no-owner only (deliberately NOT --no-privileges): the dump's
        # captured GRANT statements are exactly what a secondary role (e.g.
        # Nextcloud's own ad-hoc 'oc_admin', not the connecting POSTGRES_USER)
        # needs on these objects — stripping them left oc_admin able to log
        # in (roles dump/apply handles that) but with zero table privileges.
        # This only works because roles are applied *before* this restore
        # runs (see do_migrate) — do that first or these GRANTs fail on a
        # role that doesn't exist yet.
        proc = subprocess.run(
            [
                RUNTIME, "exec", "-i", container, "pg_restore", "-U", user, "-d", db,
                "--no-owner", "--clean", "--if-exists",
            ],
            input=dump, capture_output=True,
        )
        return proc.returncode == 0, (proc.stderr or b"").decode(errors="replace")

    def db_pg_dumpall_roles(self, container, user):
        proc = subprocess.run(
            [RUNTIME, "exec", container, "pg_dumpall", "-U", user, "--roles-only"],
            capture_output=True,
        )
        return proc.returncode == 0, proc.stdout, (proc.stderr or b"").decode(errors="replace")

    def db_psql_apply(self, container, user, db, sql):
        # No ON_ERROR_STOP: 'role already exists' for roles the fresh
        # cluster's own initdb/POSTGRES_USER already created is expected —
        # psql skips the failing statement and keeps applying the rest.
        proc = subprocess.run(
            [RUNTIME, "exec", "-i", container, "psql", "-U", user, "-d", db],
            input=sql, capture_output=True,
        )
        return proc.returncode == 0, (proc.stderr or b"").decode(errors="replace")

    def db_exec(self, container, cmd, input=None, env=None):
        args = [RUNTIME, "exec"]
        if input is not None:
            args.append("-i")
        # '-e NAME' (no '=value') makes docker copy the value from this
        # process's environment, so secrets never appear in the docker exec
        # argv on the host (visible to anyone running ps).
        run_env = None
        if env:
            run_env = {**os.environ, **env}
            for k in env:
                args += ["-e", k]
        proc = subprocess.run(args + [container] + list(cmd), input=input, capture_output=True, env=run_env)
        return proc.returncode == 0, proc.stdout, (proc.stderr or b"").decode(errors="replace")

    def compose_create(self, files, env, profile, force_recreate=False):
        from python_on_whales.exceptions import DockerException  # noqa: PLC0415
        client = self._client(files, profile)
        try:
            with self._env(env):
                client.compose.create(force_recreate=force_recreate)
            return True, ""
        except DockerException as e:
            out = f"{e.stderr or ''}\n{e.stdout or ''}"
            return False, out

    def compose_down(self, files, env, profile):
        from python_on_whales.exceptions import DockerException  # noqa: PLC0415
        client = self._client(files, profile)
        try:
            with self._env(env):
                client.compose.down()
            return True
        except DockerException as e:
            error(f"  compose down failed: {e.stderr or e}")
            return False

    def compose_pull(self, files, env):
        from python_on_whales.exceptions import DockerException  # noqa: PLC0415
        client = self._client(files, None)
        try:
            with self._env(env):
                client.compose.pull()
            return True
        except DockerException as e:
            error(f"  pull failed: {e.stderr or e}")
            return False

    def compose_logs_follow(self, files, env):
        client = self._client(files, None)
        with self._env(env):
            for _, line in client.compose.logs(follow=True, stream=True):
                print(line)

    def running_container_names(self) -> list[str]:
        return [c.name for c in self._docker.ps()]

    def all_container_names(self) -> list[str]:
        return [c.name for c in self._docker.ps(all=True)]

    def container_status(self, name: str) -> str | None:
        try:
            c = self._docker.container.inspect(name)
            return c.state.status
        except Exception:
            return None

    def container_health(self, name: str) -> str:
        try:
            c = self._docker.container.inspect(name)
            if c.state.health is None:
                return "none"
            return c.state.health.status or "none"
        except Exception:
            return "none"

    def container_healthcheck(self, name: str) -> dict:
        # Raw inspect JSON rather than python-on-whales' model, which renames
        # and type-converts these fields differently across versions.
        proc = subprocess.run([RUNTIME, "inspect", "--format={{json .Config.Healthcheck}}", name], capture_output=True, text=True)
        try:
            hc = json.loads(proc.stdout.strip() or "null")
        except json.JSONDecodeError:
            return {}
        return _healthcheck_seconds(hc)

    def container_info(self, name: str) -> dict:
        try:
            c = self._docker.container.inspect(name)
            labels = c.config.labels or {}
            config_files = labels.get("com.docker.compose.project.config_files") or ""
            return {
                "network_mode": c.host_config.network_mode or "",
                "networks": list((c.network_settings.networks or {}).keys()),
                "compose_project": labels.get("com.docker.compose.project") or "",
                "compose_service": labels.get("com.docker.compose.service") or "",
                "config_files": config_files.split(",") if config_files else [],
            }
        except Exception:
            return {}

    def volumes_for_project(self, project: str) -> list[str]:
        # Match by Compose's own naming convention (<project>_<volume-name>)
        # rather than the com.docker.compose.project label — see the
        # matching comment in SubprocessBackend for why.
        prefix = f"{project}_"
        return [v.name for v in self._docker.volume.list() if v.name.startswith(prefix)]

    def volume_exists(self, name: str) -> bool:
        return self._docker.volume.exists(name)

    def volume_create(self, name: str) -> None:
        self._docker.volume.create(name)

    def volume_remove(self, name: str) -> bool:
        try:
            self._docker.volume.remove(name)
            return True
        except Exception:
            return False

    def network_exists(self, name: str) -> bool:
        return self._docker.network.exists(name)

    def network_create(self, name: str, subnet: str | None = None) -> None:
        self._docker.network.create(name, **({"subnet": [subnet]} if subnet else {}))

    def network_subnets(self, name: str) -> list[str]:
        try:
            return [c["Subnet"] for c in (self._docker.network.inspect(name).ipam.config or []) if c.get("Subnet")]
        except Exception:
            return []

    def tar_volume_to(self, volume: str, dest_dir: Path, archive_name: str) -> bool:
        try:
            self._docker.run(
                "alpine:3.21", ["sh", "-c", f"tar czf /backup/{archive_name} -C /from ."],
                volumes=[(volume, "/from", "ro"), (dest_dir, "/backup")],
                remove=True,
            )
            return True
        except Exception as e:
            error(f"  {e}")
            return False

    def tar_dir_to(self, host_dir: Path, dest_dir: Path, archive_name: str) -> bool:
        try:
            self._docker.run(
                "alpine:3.21", ["sh", "-c", f"tar czf /backup/{archive_name} -C /from ."],
                volumes=[(host_dir, "/from", "ro"), (dest_dir, "/backup")],
                remove=True,
            )
            return True
        except Exception as e:
            error(f"  {e}")
            return False

    def untar_into_volume(self, volume: str, archive_path: Path) -> bool:
        try:
            self._docker.run(
                "alpine:3.21",
                ["sh", "-c", f"find /to -mindepth 1 -delete; tar xzf /backup/{archive_path.name} -C /to"],
                volumes=[(volume, "/to"), (archive_path.parent, "/backup")],
                remove=True,
            )
            return True
        except Exception as e:
            error(f"  {e}")
            return False

    def untar_into_dir(self, archive_path: Path, dest_dir: Path) -> bool:
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._docker.run(
                "alpine:3.21",
                ["sh", "-c", f"find /to -mindepth 1 -delete; tar xzf /backup/{archive_path.name} -C /to"],
                volumes=[(dest_dir, "/to"), (archive_path.parent, "/backup")],
                remove=True,
            )
            return True
        except Exception as e:
            error(f"  {e}")
            return False

    def archive_paths(self, mounts, members, excludes, dest_file):
        # Raw subprocess in both backends: the member list goes in on stdin,
        # which python-on-whales' run() doesn't expose.
        args = [RUNTIME, "run", "--rm", "-i"]
        for host, name in mounts.items():
            args += ["-v", f"{Path(host).resolve()}:/src/{name}:ro"]
        args += ["-v", f"{dest_file.parent.resolve()}:/out", "alpine:3.21", "sh", "-c",
                 "cd /src && tar " + " ".join(f"--exclude='{e}'" for e in excludes)
                 + f" -cf - -T - | gzip -1 > '/out/{dest_file.name}'"]
        proc = subprocess.run(args, input="\n".join(members).encode(), capture_output=True)
        return proc.returncode == 0, (proc.stderr or b"").decode(errors="replace")

    def remove_dir(self, host_dir: Path) -> bool:
        host_dir = host_dir.resolve()
        if not host_dir.exists():
            return True
        try:
            self._docker.run(
                "alpine:3.21",
                ["rm", "-rf", f"/parent/{host_dir.name}"],
                volumes=[(host_dir.parent, "/parent")],
                remove=True,
            )
        except Exception as e:
            error(f"  {e}")
            return False
        return not host_dir.exists()

    def system_prune(self) -> tuple[bool, str]:
        # Raw subprocess rather than python-on-whales here — same reasoning
        # as db_pg_dump above: this backend's main value (typed compose
        # exceptions) doesn't apply to a one-shot prune command.
        proc = subprocess.run([RUNTIME, "system", "prune", "-a", "--volumes", "-f"], capture_output=True, text=True)
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")

    def builder_prune(self) -> tuple[bool, str]:
        proc = subprocess.run([RUNTIME, "builder", "prune", "-a", "-f"], capture_output=True, text=True)
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def create_backend() -> DockerBackend:
    if DOCKER_BACKEND_NAME == "python-on-whales":
        try:
            return PythonOnWhalesBackend()
        except ImportError:
            warn(
                "DOCKER_BACKEND=python-on-whales but the package isn't installed "
                "(uv sync --extra docker-sdk) — falling back to subprocess."
            )
            return SubprocessBackend()
    return SubprocessBackend()


BACKEND: DockerBackend = create_backend()


# ── Helpers ──────────────────────────────────────────────────────────


def base_file(service: str) -> str:
    return "docker-compose.yml" if service == "landing" else "compose.yml"


def is_valid_service(service: str) -> bool:
    return service in (
        SERVICES_MIN
        + SERVICES_CORE
        + SERVICES_DAILY
        + SERVICES_BROWSER
        + SERVICES_OFFICE
        + SERVICES_AUTOMATION_AI
        + SERVICES_EXTRA
        + SERVICES_MANUAL
        + [PROXY_STANDBY]
        # Shared DB servers: valid for logs/snapshots/backup/restore by name;
        # normally started/stopped automatically (see Shared databases).
        + list(SHARED_DB_SERVICES.values())
    )


def declared_volumes(service: str) -> set[str]:
    """Top-level named volumes declared in services/<service>/compose.yml's
    own `volumes:` block (the base file only — env overrides never add
    volumes in this repo's convention). Regex-based rather than a real YAML
    parser, matching this project's pure-stdlib rule (see pyproject.toml) — good
    enough for this repo's consistently 2-space-indented compose files."""
    path = SERVICES_DIR / service / base_file(service)
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^volumes:[ \t]*$(.*?)(?=^\S|\Z)", text, re.M | re.S)
    if not m:
        return set()
    return {
        dm.group(1)
        for line in m.group(1).splitlines()
        if (dm := re.match(r"^ {2}([a-zA-Z0-9_-]+):", line))
    }


def find_orphaned_volumes(service: str) -> list[str]:
    """Docker volumes matching <service>_* that exist on this host but
    aren't declared in the service's current compose.yml — leftover from a
    prior image/volume-name change (see docs/08-maintenance.md's firefly
    example: postgres:18.4 -> postgres:18.4-alpine renamed the volume too,
    orphaning the old one, which then rode along silently in every backup)."""
    declared = declared_volumes(service)
    prefix = f"{service}_"
    orphans = []
    for v in BACKEND.volumes_for_project(service):
        short = v[len(prefix):] if v.startswith(prefix) else v
        if short not in declared:
            orphans.append(v)
    return orphans


def compose_files(service: str, env: str) -> list[Path]:
    d = SERVICES_DIR / service
    files = [d / base_file(service)]
    env_file = d / f"compose.{env}.yml"
    if env_file.is_file():
        files.append(env_file)
    if RUNTIME == "podman":
        podman_file = d / "compose.podman.yml"
        if podman_file.is_file():
            files.append(podman_file)
    return files


def compose_files_all(service: str) -> list[Path]:
    d = SERVICES_DIR / service
    files = [d / base_file(service)]
    for e in ("dev", "prod"):
        f = d / f"compose.{e}.yml"
        if f.is_file():
            files.append(f)
    if RUNTIME == "podman":
        podman_file = d / "compose.podman.yml"
        if podman_file.is_file():
            files.append(podman_file)
    return files


def compose_env(service: str) -> dict[str, str]:
    env = dict(os.environ)
    env["DATA_ROOT"] = str(SERVICE_DATA_ROOT / service)
    env["DOMAIN"] = DOMAIN
    return env


def stop_proxy_conflict(service: str, env: str) -> None:
    if service == "nginx-plain":
        conflict = "nginx"
    elif service == "nginx":
        conflict = "nginx-plain"
    else:
        return
    names = BACKEND.running_container_names()
    if any(re.match(rf"^{re.escape(conflict)}(-|$)", n) for n in names):
        warn(f"Stopping {conflict} — only one proxy can run at a time...")
        do_down(conflict, env, None, no_backup=True)
        print()


def get_running_services() -> list[str]:
    names = BACKEND.running_container_names()
    result = []
    for svc in (
        SERVICES_MIN
        + SERVICES_CORE
        + SERVICES_DAILY
        + SERVICES_BROWSER
        + SERVICES_OFFICE
        + SERVICES_AUTOMATION_AI
        + SERVICES_EXTRA
        + SERVICES_MANUAL
    ):
        if any(re.match(rf"^{re.escape(svc)}(-|$)", n) for n in names):
            result.append(svc)
    return result


# ── Shared databases (above-CORE services only) ─────────────────────
#
# Services above CORE that declare "shared_db" in services.json keep their
# database inside one shared server per engine (services/shared-postgres,
# services/shared-mariadb) instead of their own <service>-db container. CORE
# and MIN keep per-service databases. See docs/services/shared-postgres.md.
#
# Lifecycle is reference-counted at the CLI layer (main()), never inside
# do_up/do_down: do_backup, do_restore, do_up and stop_proxy_conflict all call
# do_down internally, so counting there would bounce the shared server in the
# middle of an unrelated operation. Starting is safe from anywhere (it's
# idempotent), so do_up also ensures the server for the auto-restore path;
# only stopping is counted, in release_shared_dbs() after a 'down'.
#
# The shared servers' tier ("shared") is in none of the SERVICES_* lists, so
# 'up all'/'down all', tier keywords, groups and 'status' tiers never treat
# them as ordinary services.

SHARED_DB_SERVICES = {"postgres": "shared-postgres", "mariadb": "shared-mariadb"}
_SERVICES_BY_SLUG = {s["slug"]: s for s in _SERVICES_DATA["services"]}


def shared_db_external(service: str) -> str | None:
    """The outside database host a "shared_db" app is pointed at, or None.
    Every shared_db app reads its database host from DB_HOST in its own .env
    (default: the shared server's container name). Any other value, e.g. an
    RDS / Azure / Cloud SQL endpoint, means the database lives outside this
    stack. See docs/10-new-services.md "Managed-cloud parity"."""
    spec = _SERVICES_BY_SLUG.get(service, {}).get("shared_db")
    if not spec:
        return None
    host = load_env_file(SERVICES_DIR / service / ".env").get("DB_HOST", "").strip()
    return host if host and host != SHARED_DB_SERVICES[spec["engine"]] else None


def shared_db_creds(service: str) -> dict | None:
    """Resolve a service's "shared_db" spec into concrete values. Spec values
    are key names in services/<service>/.env, or '=literal' for values the
    app hard-codes (e.g. penpot's db/user). Returns None if the service
    doesn't use a shared database, and also when its DB_HOST points outside
    the stack (shared_db_external). Every caller already treats None as "no
    shared server": nothing is started, provisioned, counted, dumped,
    restored or dropped for it."""
    spec = _SERVICES_BY_SLUG.get(service, {}).get("shared_db")
    if not spec or shared_db_external(service):
        return None
    env_vals = load_env_file(SERVICES_DIR / service / ".env")

    def resolve(key: str) -> str:
        return key[1:] if key.startswith("=") else env_vals.get(key, "")

    return {
        "engine": spec["engine"],
        "container": SHARED_DB_SERVICES[spec["engine"]],
        "db": resolve(spec["db"]),
        "user": resolve(spec["user"]),
        "password": resolve(spec["password"]),
        "extra_dbs": list(spec.get("extra_dbs", [])),
    }


def shared_admin(engine: str) -> tuple[str, str]:
    """(admin user, admin password) for a shared server, from its own .env."""
    env_vals = load_env_file(SERVICES_DIR / SHARED_DB_SERVICES[engine] / ".env")
    if engine == "postgres":
        return env_vals.get("POSTGRES_USER", "postgres"), env_vals.get("POSTGRES_PASSWORD", "")
    return "root", env_vals.get("MARIADB_ROOT_PASSWORD", "")


def _pg_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _my_ident(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def shared_sql(engine: str, sql: str, db: str | None = None) -> tuple[bool, str, str]:
    """Run SQL (sent on stdin, so passwords never hit argv) as the shared
    server's admin. Returns (success, stdout, stderr)."""
    container = SHARED_DB_SERVICES[engine]
    user, password = shared_admin(engine)
    if engine == "postgres":
        cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-tA", "-U", user, "-d", db or "postgres"]
        ok, out, err = BACKEND.db_exec(container, cmd, input=sql.encode())
    else:
        cmd = ["mariadb", "-N", "-B", "-u", user] + ([db] if db else [])
        ok, out, err = BACKEND.db_exec(container, cmd, input=sql.encode(), env={"MYSQL_PWD": password})
    return ok, out.decode(errors="replace"), err


def shared_db_exists(service: str) -> bool:
    c = shared_db_creds(service)
    if not c or BACKEND.container_status(c["container"]) != "running":
        return False
    if c["engine"] == "postgres":
        ok, out, _ = shared_sql("postgres", f"SELECT 1 FROM pg_database WHERE datname = {_sql_literal(c['db'])};")
    else:
        ok, out, _ = shared_sql("mariadb", f"SHOW DATABASES LIKE {_sql_literal(c['db'])};")
    return ok and bool(out.strip())


def ensure_shared_db(engine: str, env: str) -> bool:
    """Start the shared server for engine if it isn't already running."""
    container = SHARED_DB_SERVICES[engine]
    if BACKEND.container_status(container) == "running" and BACKEND.container_health(container) == "healthy":
        return True
    info(f"Starting shared database {container} (needed by services above CORE)...")
    return do_up(container, env, None)


def provision_shared_db(service: str) -> bool:
    """Idempotently create the service's role/user and database(s) on its
    shared server, owned by that role — what each per-service
    postgres-init/init.sh used to do on its own container. Also resets the
    password to whatever the service's .env says, so editing .env is
    enough to rotate it."""
    c = shared_db_creds(service)
    if not c:
        return True
    if not (c["db"] and c["user"] and c["password"]):
        error(f"{service}: shared_db spec in services.json didn't resolve a db/user/password from services/{service}/.env")
        return False

    dbs = [c["db"]] + c["extra_dbs"]
    if c["engine"] == "postgres":
        role, pw = _pg_ident(c["user"]), _sql_literal(c["password"])
        ok, _, err = shared_sql("postgres", f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {_sql_literal(c['user'])}) THEN
                CREATE ROLE {role} LOGIN PASSWORD {pw};
              ELSE
                ALTER ROLE {role} WITH LOGIN PASSWORD {pw};
              END IF;
            END $$;""")
        if not ok:
            error(f"{service}: couldn't create role {c['user']}: {err.strip()}")
            return False
        for db in dbs:
            ok, out, err = shared_sql("postgres", f"SELECT 1 FROM pg_database WHERE datname = {_sql_literal(db)};")
            if ok and not out.strip():
                # CREATE DATABASE can't run inside a DO block/transaction.
                ok, _, err = shared_sql("postgres", f"CREATE DATABASE {_pg_ident(db)} OWNER {role};")
            if ok:
                # Postgres grants CONNECT/TEMP on every new database to
                # PUBLIC, so without this any app's role could open any other
                # app's database (its tables stay unreadable, but it could
                # still connect and see the schema). Lock it to its owner.
                ok, _, err = shared_sql("postgres", f"REVOKE ALL ON DATABASE {_pg_ident(db)} FROM PUBLIC;")
            if ok:
                # Postgres 15+ no longer lets non-owners create objects in
                # public, so hand the schema to the app's role.
                ok, _, err = shared_sql("postgres", f"ALTER SCHEMA public OWNER TO {role}; GRANT ALL ON SCHEMA public TO {role};", db=db)
            if not ok:
                error(f"{service}: couldn't create database {db}: {err.strip()}")
                return False
    else:
        user, pw = _sql_literal(c["user"]), _sql_literal(c["password"])
        stmts = [f"CREATE USER IF NOT EXISTS {user}@'%' IDENTIFIED BY {pw};", f"ALTER USER {user}@'%' IDENTIFIED BY {pw};"]
        for db in dbs:
            stmts.append(f"CREATE DATABASE IF NOT EXISTS {_my_ident(db)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            stmts.append(f"GRANT ALL PRIVILEGES ON {_my_ident(db)}.* TO {user}@'%';")
        stmts.append("FLUSH PRIVILEGES;")
        ok, _, err = shared_sql("mariadb", "\n".join(stmts))
        if not ok:
            error(f"{service}: couldn't create database/user on shared-mariadb: {err.strip()}")
            return False
    return True


def shared_db_ready(service: str, env: str, provision: bool = True) -> bool:
    """Called by every function that can start an app (do_up, do_update,
    do_restart, do_restore): start the app's shared server if needed, then
    provision its database. No-op for services without "shared_db". Safe to
    call from anywhere — starting is idempotent; only stopping is
    reference-counted (release_shared_dbs, from main())."""
    ext = shared_db_external(service)
    if ext:
        info(f"{service}: database on outside host {ext} (DB_HOST) — shared server not used")
        return True
    c = shared_db_creds(service)
    if not c:
        return True
    if not ensure_shared_db(c["engine"], env):
        error(f"{c['container']} failed to start — {service} can't come up without it")
        return False
    return provision_shared_db(service) if provision else True


def release_shared_dbs(env: str) -> None:
    """After a 'down': stop each shared server no running service still uses."""
    running = get_running_services()
    for engine, container in SHARED_DB_SERVICES.items():
        if BACKEND.container_status(container) != "running":
            continue
        users = [s for s in running if (c := shared_db_creds(s)) and c["engine"] == engine]
        if users:
            info(f"{container} stays up — still used by: {', '.join(users)}")
            continue
        info(f"No running service uses {container} any more — stopping it...")
        do_down(container, env, None)


def dump_shared_db(service: str, dest_dir: Path, ts: str) -> Path | None:
    """Logical dump of the service's own database(s) on its shared server into
    dest_dir — the per-app part of a snapshot (a volume tar of the shared
    server would hold every app's data at once). Postgres: one custom-format
    file per database; MariaDB: one SQL file per database."""
    c = shared_db_creds(service)
    if not c or BACKEND.container_status(c["container"]) != "running":
        return None
    admin_user, admin_pw = shared_admin(c["engine"])
    last = None
    for db in [c["db"]] + c["extra_dbs"]:
        if c["engine"] == "postgres":
            ok, data, err = BACKEND.db_pg_dump(c["container"], admin_user, db)
            fname = f"{service}_shareddb_{db}_{ts}.dump"
        else:
            ok, data, err = BACKEND.db_exec(
                c["container"],
                ["mariadb-dump", "-u", admin_user, "--single-transaction", "--routines", "--triggers", db],
                env={"MYSQL_PWD": admin_pw},
            )
            fname = f"{service}_shareddb_{db}_{ts}.sql"
        if not ok:
            error(f"  failed to dump {db} from {c['container']}: {err.strip()}")
            continue
        (dest_dir / fname).write_bytes(data)
        last = dest_dir / fname
        shown = dest_dir.relative_to(BASE_DIR) if dest_dir.is_relative_to(BASE_DIR) else dest_dir
        success(f"  {c['container']}/{db} -> {shown}/{fname}")
    return last


def restore_shared_db(service: str, snap_dir: Path) -> bool:
    """Replace the service's database(s) on its shared server with the dumps
    in snap_dir: drop, re-provision (fresh empty db owned by the app's role),
    then load. The app must be stopped (do_restore guarantees this)."""
    c = shared_db_creds(service)
    files = sorted(snap_dir.glob(f"{service}_shareddb_*"))
    if not c or not files:
        return True
    admin_user, admin_pw = shared_admin(c["engine"])
    ok = True
    for db in [c["db"]] + c["extra_dbs"]:
        f = next((p for p in files if p.name.startswith(f"{service}_shareddb_{db}_")), None)
        if not f:
            continue
        if c["engine"] == "postgres":
            shared_sql("postgres", f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = {_sql_literal(db)};")
            dropped, _, err = shared_sql("postgres", f"DROP DATABASE IF EXISTS {_pg_ident(db)};")
        else:
            dropped, _, err = shared_sql("mariadb", f"DROP DATABASE IF EXISTS {_my_ident(db)};")
        if not dropped or not provision_shared_db(service):
            error(f"  couldn't reset {db} on {c['container']}: {err.strip()}")
            ok = False
            continue
        if c["engine"] == "postgres":
            # --role: objects are created as the app's role (the admin can
            # SET ROLE to it), so the app owns everything it owned before.
            loaded, _, err = BACKEND.db_exec(
                c["container"],
                ["pg_restore", "-U", admin_user, "-d", db, "--no-owner", "--role", c["user"]],
                input=f.read_bytes(),
            )
        else:
            loaded, _, err = BACKEND.db_exec(
                c["container"], ["mariadb", "-u", admin_user, db], input=f.read_bytes(), env={"MYSQL_PWD": admin_pw},
            )
        if loaded:
            success(f"  restored {db} on {c['container']}")
        else:
            error(f"  failed to restore {db} on {c['container']}: {err.strip()}")
            ok = False
    return ok


def drop_shared_db(service: str) -> bool:
    """Remove the service's database(s) and its login from its shared server
    (reset only — never called on the normal down/up path). Other apps'
    databases on the same server are untouched."""
    c = shared_db_creds(service)
    if not c or BACKEND.container_status(c["container"]) != "running":
        return True
    ok = True
    for db in [c["db"]] + c["extra_dbs"]:
        if c["engine"] == "postgres":
            shared_sql("postgres", f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = {_sql_literal(db)};")
            dropped, _, err = shared_sql("postgres", f"DROP DATABASE IF EXISTS {_pg_ident(db)};")
        else:
            dropped, _, err = shared_sql("mariadb", f"DROP DATABASE IF EXISTS {_my_ident(db)};")
        if not dropped:
            error(f"  couldn't drop {db} on {c['container']}: {err.strip()}")
            ok = False
    if c["engine"] == "postgres":
        dropped, _, err = shared_sql("postgres", f"DROP ROLE IF EXISTS {_pg_ident(c['user'])};")
    else:
        dropped, _, err = shared_sql("mariadb", f"DROP USER IF EXISTS {_sql_literal(c['user'])}@'%';")
    if not dropped:
        error(f"  couldn't drop login {c['user']} on {c['container']}: {err.strip()}")
        ok = False
    return ok


def do_status() -> int:
    running = set(get_running_services())
    all_services = (
        SERVICES_MIN
        + SERVICES_CORE
        + SERVICES_DAILY
        + SERVICES_BROWSER
        + SERVICES_OFFICE
        + SERVICES_AUTOMATION_AI
        + SERVICES_EXTRA
        + SERVICES_MANUAL
    )

    def show_tier(label: str, services: list[str]) -> None:
        if not services:
            return
        print(f"  {BOLD}{label}:{RESET}")
        for s in services:
            marker = f"{GREEN}●{RESET}" if s in running else "○"
            print(f"    {marker} {s}")
        print()

    header("Service status (● running, ○ stopped):")
    show_tier("MIN", SERVICES_MIN)
    show_tier("CORE", SERVICES_CORE)
    show_tier("DAILY", SERVICES_DAILY)
    show_tier("BROWSER", SERVICES_BROWSER)
    show_tier("OFFICE", SERVICES_OFFICE)
    show_tier("AUTOMATION-AI", SERVICES_AUTOMATION_AI)
    show_tier("EXTRA", SERVICES_EXTRA)
    show_tier("MANUAL", SERVICES_MANUAL)

    print(f"  {BOLD}SHARED DATABASES (started/stopped automatically with the services that use them):{RESET}")
    for engine, container in SHARED_DB_SERVICES.items():
        up = BACKEND.container_status(container) == "running"
        users = [s for s in all_services if (c := shared_db_creds(s)) and c["engine"] == engine]
        live = [s for s in users if s in running]
        marker = f"{GREEN}●{RESET}" if up else "○"
        print(f"    {marker} {container} — used by {len(users)} service(s){', running: ' + ' '.join(live) if live else ''}")
    print()
    success(f"{len(running)}/{len(all_services)} service(s) running")

    def show_group(name: str, indent: int) -> None:
        members = SERVICE_GROUPS[name]
        up = sum(1 for s in members if s in running)
        print(f"{'  ' * indent}{BOLD}{name}{RESET} ({up}/{len(members)} running): {' '.join(members)}")

    print()
    print(f"  {BOLD}Groups ({len(SERVICE_GROUPS)} — 'up group:<name>' / 'precreate group:<name>' starts exactly these):{RESET}")
    categories = {s.get("category") for s in _SERVICES_DATA["services"] if s.get("tier") and s.get("category")}
    for cat in sorted(categories):
        show_group(cat, indent=2)
        for sub in sorted(CATEGORY_SUBGROUPS.get(cat, [])):
            show_group(sub, indent=3)

    return 0


# ── Wait for healthy ─────────────────────────────────────────────────


def health_deadline(container: str) -> int:
    """How long to wait for container to turn healthy: as long as Docker
    itself would before calling it unhealthy (start_period plus retries
    rounds of interval+timeout, from its compose or image healthcheck), but
    never less than HEALTH_TIMEOUT. A fixed 180s made first boots that run
    long migrations (Grafana, Coolify, GitLab) look like failures even
    though they came up fine (2026-10-02 fresh-install run)."""
    hc = BACKEND.container_healthcheck(container)
    if not hc:
        return HEALTH_TIMEOUT
    return int(max(HEALTH_TIMEOUT, hc["start_period"] + hc["retries"] * (hc["interval"] + hc["timeout"]) + 30))


def wait_healthy(service: str) -> bool:
    all_names = BACKEND.all_container_names()

    container = next((n for n in all_names if n == service), None)
    if not container:
        candidates = [
            n for n in all_names
            if re.match(rf"^{re.escape(service)}-", n) and not re.search(r"db|redis|worker", n)
        ]
        container = candidates[0] if candidates else None
    if not container:
        container = service

    deadline = health_deadline(container)
    print(f"  {CYAN}waiting for {service} to be ready...", end="", flush=True)

    elapsed = 0
    interval = 5
    while elapsed < deadline:
        status = BACKEND.container_status(container) or ""
        health = BACKEND.container_health(container)

        if health == "healthy":
            print(f" ready ({elapsed}s){RESET}")
            return True
        if health == "none" and status == "running":
            print(f" ready ({elapsed}s){RESET}")
            return True
        if status in ("exited", "dead"):
            print(f" exited{RESET}")
            return False
        if status == "created":
            print(f" dependency failed{RESET}")
            return False

        time.sleep(interval)
        elapsed += interval
        print(".", end="", flush=True)

    print(f" timeout after {deadline}s{RESET}")
    return False


def wait_container_healthy(container: str, timeout: int | None = None) -> bool:
    """Like wait_healthy but for one exact container name — no fuzzy matching,
    used by do_migrate to wait on a freshly-started <service>-db alone."""
    print(f"  {CYAN}waiting for {container} to be ready...", end="", flush=True)

    if timeout is None:
        timeout = health_deadline(container)
    elapsed = 0
    interval = 5
    while elapsed < timeout:
        status = BACKEND.container_status(container) or ""
        health = BACKEND.container_health(container)

        if health == "healthy":
            print(f" ready ({elapsed}s){RESET}")
            return True
        if health == "none" and status == "running":
            print(f" ready ({elapsed}s){RESET}")
            return True
        if status in ("exited", "dead"):
            print(f" exited{RESET}")
            return False

        time.sleep(interval)
        elapsed += interval
        print(".", end="", flush=True)

    print(f" timeout after {timeout}s{RESET}")
    return False


# ── Backup / snapshots ───────────────────────────────────────────────


SNAPSHOT_NAME = re.compile(r"^\d{8}-\d{6}$")


def list_snapshots(service: str) -> list[Path]:
    """Snapshot directories for a service, oldest first (names sort correctly
    since they're YYYYMMDD-HHMMSS). Only timestamp-named directories count:
    a hand-made folder next to them (e.g. nextcloud's
    'pre-upgrade-fix-20260817-232941') sorts after every timestamp ('p' > '2'),
    so it used to be taken as the *newest* snapshot — restore/auto-restore
    would have loaded August's data, and pruning would have deleted real
    recent snapshots first (found 2026-10-02). Such folders are left alone:
    never restored by default, never pruned; restore one explicitly with
    --snapshot <name>."""
    svc_dir = BACKUP_ROOT / service
    if not svc_dir.is_dir():
        return []
    return sorted(p for p in svc_dir.iterdir() if p.is_dir() and SNAPSHOT_NAME.match(p.name))


RESET_BACKUP_NAME = re.compile(r"^reset-backup-\d{8}-\d{6}$")


def list_reset_backups(service: str) -> list[Path]:
    """reset-backup-<ts> folders for a service, oldest first. Kept apart
    from regular snapshots (list_snapshots ignores them), so neither
    'restore <service>' nor BACKUP_RETENTION ever touches them."""
    svc_dir = BACKUP_ROOT / service
    if not svc_dir.is_dir():
        return []
    return sorted(p for p in svc_dir.iterdir() if p.is_dir() and RESET_BACKUP_NAME.match(p.name))


def prune_reset_backups(service: str) -> None:
    if RESET_BACKUP_RETENTION == -1:
        return
    backups = list_reset_backups(service)
    for old in backups[: max(0, len(backups) - RESET_BACKUP_RETENTION)]:
        shutil.rmtree(old, ignore_errors=True)


def prune_snapshots(service: str) -> None:
    if BACKUP_RETENTION == -1:
        return
    snaps = list_snapshots(service)
    excess = max(0, len(snaps) - BACKUP_RETENTION)
    for old in snaps[:excess]:
        shutil.rmtree(old, ignore_errors=True)


def backup_service(service: str) -> None:
    """Tar every named volume + the service's data dir into a new timestamped
    snapshot, then prune old snapshots beyond BACKUP_RETENTION."""
    vols = BACKEND.volumes_for_project(service)
    service_data_dir = SERVICE_DATA_ROOT / service
    has_shared_db = bool(shared_db_creds(service)) and shared_db_exists(service)
    ext = shared_db_external(service)
    if ext:
        warn(f"{service}: database is on outside host {ext} (DB_HOST) — not in this snapshot; use that provider's backups")

    if not vols and not service_data_dir.is_dir() and not has_shared_db:
        return  # nothing to back up

    declared = declared_volumes(service)
    prefix = f"{service}_"
    for v in vols:
        short = v[len(prefix):] if v.startswith(prefix) else v
        if short not in declared:
            warn(f"{v} is backed up but not declared in services/{service}/{base_file(service)}")
            warn(f"  likely orphaned from a prior image/volume-name change — once you're sure you don't need it: docker volume rm {v}")
            warn(f"  (or: python homeserver.py orphaned-volumes {service} --yes)")

    ts = time.strftime("%Y%m%d-%H%M%S")
    snap_dir = BACKUP_ROOT / service / ts
    snap_dir.mkdir(parents=True, exist_ok=True)
    info(f"Backing up {service} -> service_data/backup/{service}/{ts}/")

    # Timestamp in the filename too (not just the parent dir) so a file keeps
    # its identity if ever copied/moved out of its snapshot folder.
    for v in vols:
        fname = f"{v}_{ts}.tar.gz"
        if BACKEND.tar_volume_to(v, snap_dir, fname):
            success(f"  {v} -> service_data/backup/{service}/{ts}/{fname}")
        else:
            error(f"  failed to back up volume {v}")

    if service_data_dir.is_dir():
        fname = f"service_data_{ts}.tar.gz"
        BACKEND.tar_dir_to(service_data_dir, snap_dir, fname)
        success(f"  service_data -> service_data/backup/{service}/{ts}/{fname}")

    # The app's own database(s) on its shared server, as logical dumps.
    if has_shared_db:
        dump_shared_db(service, snap_dir, ts)

    prune_snapshots(service)


def list_dumps(service: str) -> list[Path]:
    """Dump directories for a service, oldest first — mirrors list_snapshots.
    Not subject to BACKUP_RETENTION pruning: these are one-off manual dumps
    for a migration, not part of the regular snapshot rotation."""
    svc_dir = DB_DUMP_ROOT / service
    if not svc_dir.is_dir():
        return []
    return sorted(p for p in svc_dir.iterdir() if p.is_dir())


def do_snapshots(service: str) -> None:
    snaps = list_snapshots(service)
    if not snaps:
        warn(f"No snapshots found for {service}")
        return
    info(f"Snapshots for {service} (newest last):")
    for snap in snaps:
        size_bytes = sum(f.stat().st_size for f in snap.rglob("*") if f.is_file())
        size_mb = size_bytes / (1024 * 1024)
        print(f"  {snap.name}  ({size_mb:.1f} MB)")


# ── Actions ──────────────────────────────────────────────────────────


def wg_tunnel_up() -> bool:
    """True once wg-easy's wg0 interface actually holds 10.8.0.1 — the
    address every prod compose.prod.yml also binds each port to (see
    docs/09-firewall.md). Missing 'ip' (e.g. non-Linux) is treated as
    "can't tell" rather than "not up", so the caller doesn't loop pointlessly."""
    if not shutil.which("ip"):
        return True
    try:
        out = subprocess.run(["ip", "-o", "addr", "show", "wg0"], capture_output=True, text=True, timeout=5)
        return out.returncode == 0 and "10.8.0.1" in out.stdout
    except Exception:
        return True


# Set by --no-wg: this invocation never starts wg-easy as a side effect.
NO_WG_START = False


def nonlocal_bind_enabled() -> bool:
    """net.ipv4.ip_nonlocal_bind=1 (docker/host-boot-safety.sh): a service can
    bind 10.8.0.1 before wg0 exists. Unreadable (non-Linux) counts as fine."""
    try:
        return Path("/proc/sys/net/ipv4/ip_nonlocal_bind").read_text().strip() == "1"
    except OSError:
        return True


def ensure_wg_tunnel_ready(service: str, env: str) -> None:
    """Every other prod service binds a second port to wg-easy's 10.8.0.1
    tunnel address, which only exists once wg-easy has brought up wg0. On a
    cold start (or the Docker daemon auto-restarting 'unless-stopped'
    containers after a reboot) another service can win that race and fail
    to bind at all. services.json's list order only protects bulk 'up
    <tier>' calls, not a single-service 'up' — so check directly instead."""
    if env != "prod" or service == "wg-easy" or wg_tunnel_up():
        return
    if NO_WG_START:
        # --no-wg: wg-easy stays as it is (e.g. stopped on purpose). Binding
        # 10.8.0.1 then only works with ip_nonlocal_bind=1.
        if nonlocal_bind_enabled():
            info("--no-wg: not starting wg-easy; 10.8.0.1 isn't up, binds to it rely on net.ipv4.ip_nonlocal_bind=1")
        else:
            warn("--no-wg: not starting wg-easy, but net.ipv4.ip_nonlocal_bind is 0, so the 10.8.0.1 port binds "
                 "will fail: run docker/host-boot-safety.sh (docs/08-maintenance.md 'Boot safety') or start wg-easy")
        return
    info("wg-easy's tunnel address (10.8.0.1) isn't up yet — starting wg-easy first...")
    do_up("wg-easy", env, None)
    for _ in range(30):
        if wg_tunnel_up():
            return
        time.sleep(1)
    warn("wg-easy's tunnel address (10.8.0.1) still isn't up after 30s — continuing anyway")


def fstab_mountpoints() -> list[str]:
    """Non-root mountpoints declared in /etc/fstab, longest first. Empty on
    hosts without an fstab (Windows/macOS) — the mount check below then
    becomes a no-op rather than a false alarm."""
    fstab = Path("/etc/fstab")
    if not fstab.is_file():
        return []
    mps = []
    for line in fstab.read_text().splitlines():
        fields = line.split()
        if len(fields) >= 2 and not fields[0].startswith("#") and fields[1].startswith("/") and fields[1] != "/":
            mps.append(fields[1])
    return sorted(set(mps), key=len, reverse=True)


def check_data_mounts(service: str) -> bool:
    """Refuse to start a service whose host data paths sit on an fstab mount
    that isn't mounted, or is mounted read-only. Both data drives here are
    'nofail', so the host boots fine without them — and a container started
    then silently binds the empty directory *under* the mountpoint (writes
    land on the root disk), or gets EROFS on every upload (NTFS falls back to
    read-only after a Windows Fast Startup/hibernate). Checks DATA_ROOT plus
    every path-valued var in the service's own .env (UPLOAD_LOCATION,
    MEDIA_ROOT, ...), since those secondary roots aren't auto-injected."""
    mountpoints = fstab_mountpoints()
    if not mountpoints:
        return True
    svc_dir = SERVICES_DIR / service
    paths = [SERVICE_DATA_ROOT / service]
    for key, val in load_env_file(svc_dir / ".env").items():
        if key != "DATA_ROOT" and val.startswith(("/", "./", "../")):
            paths.append(svc_dir / val)

    problems = set()
    for p in paths:
        real = os.path.realpath(p)
        mp = next((m for m in mountpoints if real == m or real.startswith(m + "/")), None)
        if mp is None:
            continue
        if not os.path.ismount(mp):
            problems.add(f"{mp} is not mounted (needed by {real})")
        elif os.statvfs(mp).f_flag & os.ST_RDONLY:
            problems.add(f"{mp} is mounted read-only (needed by {real})")
    for msg in sorted(problems):
        error(f"{service}: {msg}")
    if problems:
        error(f"Not starting {service} — fix the mount first (see docs/08-maintenance.md 'Boot safety')")
    return not problems


def restore_lost_state(service: str) -> None:
    """The partial-loss case do_up's auto-restore does not cover: service_data/data/<service>/ survived (it
    lives on the HDD) but the Docker volumes (on the SSD) are gone, e.g. after an SSD wipe. The auto-restore
    only fires when the data folder, the volumes AND the database are all missing, so such a service started
    against an empty database, and the next nightly snapshot then recorded that empty state and would
    have pruned the good ones (Uptime Kuma, 2026-10-06). So: restore each named volume the newest snapshot
    holds and Docker lacks, and a shared database that is gone. Present volumes are never touched."""
    snaps = list_snapshots(service)
    if not snaps:
        return
    latest = snaps[-1]
    ts_suffix = re.compile(r"_\d{8}-\d{6}$")
    for f in sorted(latest.glob("*.tar.gz")):
        base = ts_suffix.sub("", f.name[: -len(".tar.gz")])
        if base == "service_data" or BACKEND.volume_exists(base):
            continue
        info(f"{service}: volume {base} is missing but snapshot {latest.name} holds it — restoring it before starting (pass --fresh to start blank instead)...")
        BACKEND.volume_create(base)
        if not BACKEND.untar_into_volume(base, f):
            error(f"  failed to restore volume {base}")
    c = shared_db_creds(service)
    if c and any(latest.glob(f"{service}_shareddb_*")) and not shared_db_exists(service):
        info(f"{service}: its database on {c['container']} is missing but snapshot {latest.name} holds it — restoring it before starting...")
        restore_shared_db(service, latest)


def do_up(service: str, env: str, profile: str | None, exclude: list[str] | None = None, fresh: bool = False) -> bool:
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False

    if not check_data_mounts(service):
        return False
    ensure_wg_tunnel_ready(service, env)

    # Start the app's shared database server (if it uses one) before the
    # auto-restore check below, which needs to ask it whether the app's
    # database exists. Provisioning waits until after that check — creating
    # the database first would make a fresh app look like it has data.
    if not shared_db_ready(service, env, provision=False):
        return False

    if not fresh:
        service_data_dir = SERVICE_DATA_ROOT / service
        # Cheap dir check first — only pay for the docker-volume-ls call when
        # the dir is already missing ('and' short-circuits), so a routine up
        # on an already-live service skips the subprocess call entirely.
        # do_restore is defined later in the file but that's fine — resolved
        # at call time, not def time. Its own was_running branch may call
        # back into do_up once if a live container's volume was deleted out
        # from under it — safe, terminates because restored state is no
        # longer "fresh" on that second pass.
        if (
            not service_data_dir.is_dir()
            and not BACKEND.volumes_for_project(service)
            and not (shared_db_creds(service) and shared_db_exists(service))
        ):
            snaps = list_snapshots(service)
            if snaps:
                info(f"{service} has no live volumes or data on disk — restoring latest snapshot ({snaps[-1].name}) before starting (pass --fresh to start blank instead)...")
                do_restore(service, env, profile)
        else:
            restore_lost_state(service)

    if not provision_shared_db(service):
        return False

    stop_proxy_conflict(service, env)
    # Landing bakes env vars into HTML at startup; nginx-plain runs envsubst
    # on templates. Both need a full container restart to pick up config
    # changes — this is an internal config-reload mechanic, not the user
    # asking to stop the service, so skip the auto-backup for it.
    if service in ("landing", "nginx-plain"):
        do_down(service, env, None, no_backup=True)

    files = compose_files(service, env)
    cenv = compose_env(service)

    if profile:
        info(f"Starting {service} ({env}) --profile {profile}...")
    elif exclude:
        info(f"Starting {service} ({env}), excluding {', '.join(exclude)}...")
    else:
        info(f"Starting {service} ({env})...")

    ok, out = BACKEND.compose_up(files, cenv, profile, exclude=exclude)
    if out:
        print(out)

    if not ok:
        m = re.search(r"listen tcp [^:]+:(\d+)", out)
        if m:
            port = m.group(1)
            warn(f"Port {port} in use — freeing process and retrying...")
            if shutil.which("fuser"):
                subprocess.run(["sudo", "fuser", "-k", f"{port}/tcp"], capture_output=True)
            time.sleep(1)
            ok, out = BACKEND.compose_up(files, cenv, profile, exclude=exclude)
        # Podman quirk: 'internal libpod error' is thrown during dependency-
        # chain tracking but containers still start. Fall through to
        # wait_healthy to verify actual container state rather than treating
        # it as a hard failure.
        if not ok:
            if "internal libpod error" not in out:
                return False
            warn("Podman dependency tracking error — checking container status...")

    return wait_healthy(service)


def do_precreate(service: str, env: str, profile: str | None, update: bool = False) -> bool:
    """Creates a service's containers without starting them — so it shows
    up as a stack in Portainer (which auto-detects any compose project by
    its container labels, running or not) and can be started from there
    later, without ever needing Portainer's own API/credentials. Skips
    services that already have containers (running or previously started)
    so this never touches/recreates anything already in use — unless
    update=True (--update), which force-recreates a not-currently-running
    service's containers so a later .env/compose edit actually takes
    effect. Still refuses to touch a service that's currently running —
    use 'up' (which force-recreates on config change) for that instead."""
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False

    all_names = BACKEND.all_container_names()
    has_containers = any(re.match(rf"^{re.escape(service)}(-|$)", n) for n in all_names)
    if has_containers and not update:
        info(f"{service} already has containers — skipping (use 'up' to start it, or 'precreate --update' to rebuild)")
        return True
    if has_containers and service in get_running_services():
        warn(f"{service} is currently running — skipping (stop it first, or use 'up' to apply the new .env)")
        return True

    files = compose_files(service, env)
    cenv = compose_env(service)
    # Precreate everything a service defines, including profile-gated
    # containers (e.g. GitLab's runner profile) — the point is
    # making the whole thing visible/startable in Portainer, not
    # replicating 'up's normal profile-gating.
    cenv.setdefault("COMPOSE_PROFILES", "*")

    verb = "Rebuilding" if (has_containers and update) else "Pre-creating"
    if profile:
        info(f"{verb} {service} ({env}) --profile {profile}...")
    else:
        info(f"{verb} {service} ({env})...")

    ok, out = BACKEND.compose_create(files, cenv, profile, force_recreate=update)
    if out:
        print(out)
    return ok


def do_down(service: str, env: str, profile: str | None, no_backup: bool = False, force_snapshot: bool = False) -> bool:
    # env is unused here (compose_files_all tears down both dev/prod
    # regardless) — kept in the signature so do_up/do_down/do_update/
    # do_restart/do_backup/do_restore all share one uniform call shape.
    #
    # Snapshot only if the service was actually running: a stopped service's
    # last snapshot (taken when it stopped) is still current, and
    # re-snapshotting it just churns BACKUP_RETENTION (pushing out older,
    # different snapshots) and — for a shared-db app whose server is down —
    # writes an incomplete one with no database dump (both seen 2026-10-02
    # after a `down all`). do_backup/do_reset pass force_snapshot=True: an
    # explicit backup, or a reset about to delete data, always snapshots.
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False

    was_running = any(re.match(rf"^{re.escape(service)}(-|$)", n) for n in BACKEND.running_container_names())
    files = compose_files_all(service)
    cenv = compose_env(service)

    if profile:
        info(f"Stopping {service} --profile {profile}...")
    else:
        info(f"Stopping {service}...")
    BACKEND.compose_down(files, cenv, profile)

    success(f"{service} stopped")

    if no_backup:
        pass
    elif was_running or force_snapshot:
        backup_service(service)
    else:
        info(f"  {service} was already stopped — its last snapshot is still current, not taking another")

    return True


def do_update(service: str, env: str, profile: str | None = None) -> bool:
    # profile is unused — update always pulls/recreates the base service, no
    # profile-scoped variant — kept for the same uniform call shape as above.
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False
    if not check_data_mounts(service):
        return False

    if not shared_db_ready(service, env):
        return False

    files = compose_files(service, env)
    cenv = compose_env(service)

    info(f"Pulling latest images for {service}...")
    if not BACKEND.compose_pull(files, cenv):
        warn(f"Pull had issues for {service} — continuing with recreate anyway")

    info(f"Recreating {service} ({env})...")
    ok, out = BACKEND.compose_up(files, cenv, None, force_recreate=True)
    if out:
        print(out)
    if not ok:
        return False

    return wait_healthy(service)


def do_restart(service: str, env: str, profile: str | None) -> bool:
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False
    if not check_data_mounts(service):
        return False

    if not shared_db_ready(service, env):
        return False

    files = compose_files(service, env)
    cenv = compose_env(service)

    if profile:
        info(f"Restarting {service} ({env}) --profile {profile}...")
    else:
        info(f"Restarting {service} ({env})...")

    ok, out = BACKEND.compose_up(files, cenv, profile, force_recreate=True)
    if out:
        print(out)
    if not ok:
        return False

    return wait_healthy(service)


def do_backup(service: str, env: str, profile: str | None) -> bool:
    """Explicit backup command — 'down' now backs up automatically as part of
    stopping, so this just reuses that: stop (which snapshots), then restart
    if it was running. Kept as its own command for backing up without wanting
    to think about whether the service happens to be running right now."""
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False

    was_running = service in get_running_services()

    # A stopped app's shared server may be down too; the snapshot needs it
    # up to dump the app's database. main() releases it again afterwards.
    if not shared_db_ready(service, env, provision=False):
        return False

    do_down(service, env, profile, no_backup=False, force_snapshot=True)
    if was_running:
        do_up(service, env, profile)

    return True


def do_restore(service: str, env: str, profile: str | None, snapshot: str | None = None) -> bool:
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False

    if snapshot:
        backup_dir = BACKUP_ROOT / service / snapshot
        if not backup_dir.is_dir():
            error(f"Snapshot '{snapshot}' not found for {service} (run: snapshots {service} to list them)")
            return False
    else:
        snaps = list_snapshots(service)
        if not snaps:
            warn(f"No backup found for {service} — skipping")
            return True
        backup_dir = snaps[-1]

    # Back up whatever's there right now before overwriting it — do_down
    # does this automatically as part of stopping.
    was_running = service in get_running_services()
    if was_running:
        do_down(service, env, profile, no_backup=False)

    info(f"Restoring {service} from snapshot {backup_dir.name}...")
    ok = True
    # Archive names end in _<YYYYMMDD-HHMMSS> (the moment they were taken).
    # Strip that from the file name itself, not "_<folder name>": a snapshot
    # folder renamed to keep it out of pruning (e.g. pre-fresh-install-<ts>)
    # would otherwise restore into volumes named "<vol>_<ts>".
    ts_suffix_re = re.compile(r"_\d{8}-\d{6}$")
    for f in sorted(backup_dir.glob("*.tar.gz")):
        base = f.name[: -len(".tar.gz")]
        # Newer snapshots suffix the filename with the timestamp too (e.g.
        # 'service_data_20260730-071152.tar.gz') — strip it to recover the
        # plain name. Older snapshots (pre-dating this) have no suffix, so
        # this is a no-op for them — both forms restore correctly.
        base = ts_suffix_re.sub("", base)
        if base == "service_data":
            service_data_dir = SERVICE_DATA_ROOT / service
            if BACKEND.untar_into_dir(f, service_data_dir):
                success(f"  restored service_data for {service}")
            else:
                error(f"  failed to restore service_data for {service}")
                ok = False
        else:
            if not BACKEND.volume_exists(base):
                BACKEND.volume_create(base)
            if BACKEND.untar_into_volume(base, f):
                success(f"  restored volume {base}")
            else:
                error(f"  failed to restore volume {base}")
                ok = False

    if any(backup_dir.glob(f"{service}_shareddb_*")):
        if shared_db_ready(service, env, provision=False):
            if not restore_shared_db(service, backup_dir):
                ok = False
        else:
            ok = False

    # Mirror do_backup: put the service back the way it was found, so
    # 'restore' never leaves something the caller didn't ask to stop.
    if was_running:
        do_up(service, env, profile)

    return ok


def do_reset(service: str, env: str, profile: str | None) -> bool:
    """Fresh start with a safety net: snapshot everything the service owns,
    verify the snapshot really holds it, then wipe exactly that service and
    start it blank. 'restore <service>' undoes it.

    Wipes: the service's named volumes, service_data/data/<service>/, and —
    for an app on a shared database server — its own database(s) and login
    there (other apps on that server are untouched). Does NOT touch secondary
    data roots outside service_data/data (immich UPLOAD_LOCATION, jellyfin
    MEDIA_ROOT, ...): those hold bulk media, not app state."""
    if service in SHARED_DB_SERVICES.values():
        error(f"{service} is a shared database server — reset the services that use it instead")
        return False
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return False

    c = shared_db_creds(service)
    ext = shared_db_external(service)
    if ext:
        warn(f"{service}: its database on outside host {ext} (DB_HOST) is NOT wiped or snapshotted by reset —")
        warn("  reset it on that provider if a truly fresh start is wanted.")
    # The snapshot below needs the shared server up to dump the app's database.
    if c and not shared_db_ready(service, env, provision=False):
        return False

    vols = BACKEND.volumes_for_project(service)
    data_dir = SERVICE_DATA_ROOT / service
    has_db = bool(c) and shared_db_exists(service)
    before = set(list_snapshots(service))

    # 1. Snapshot (do_down stops the service and snapshots it, whether or
    #    not it was running — stopped containers still hold volumes).
    info(f"Resetting {service}: snapshotting first...")
    do_down(service, env, profile or "*", no_backup=False, force_snapshot=True)

    # 2. Verify the snapshot holds everything about to be deleted. Pruning
    #    can't remove it: it's the newest.
    if vols or data_dir.is_dir() or has_db:
        new = sorted(set(list_snapshots(service)) - before)
        if not new:
            error(f"  no snapshot was written for {service} — nothing deleted")
            return False
        names = {p.name for p in new[-1].iterdir()}
        missing = [v for v in vols if not any(n.startswith(f"{v}_") for n in names)]
        if data_dir.is_dir() and not any(n.startswith("service_data_") for n in names):
            missing.append("service_data")
        if has_db and not any(n.startswith(f"{service}_shareddb_") for n in names):
            missing.append(f"{c['container']}/{c['db']}")
        if missing:
            error(f"  snapshot {new[-1].name} is missing {', '.join(missing)} — nothing deleted")
            return False
        success(f"  snapshot verified: service_data/backup/{service}/{new[-1].name}/")
        # Keep it out of regular retention: it's the only copy of the data
        # about to be wiped, and later downs/backups would otherwise push it
        # out. Renamed, not copied — same data, no extra disk.
        kept = new[-1].with_name(f"reset-backup-{new[-1].name}")
        new[-1].rename(kept)
        prune_reset_backups(service)
        success(f"  kept as service_data/backup/{service}/{kept.name}/ (never pruned by BACKUP_RETENTION; newest {RESET_BACKUP_RETENTION} reset backups kept)")
    else:
        kept = None

    # 3. Wipe exactly this service.
    ok = True
    for v in vols:
        if BACKEND.volume_remove(v):
            success(f"  removed volume {v}")
        else:
            error(f"  couldn't remove volume {v}")
            ok = False
    if data_dir.is_dir():
        if BACKEND.remove_dir(data_dir):
            success(f"  removed service_data/data/{service}/")
        else:
            error(f"  couldn't remove service_data/data/{service}/")
            ok = False
    if has_db and drop_shared_db(service):
        success(f"  dropped {service}'s database and login on {c['container']}")
    elif has_db:
        ok = False
    if not ok:
        error(f"  {service} was only partly wiped — not starting it; 'restore {service}' brings the snapshot back")
        return False

    # 4. Start blank (provisioning creates a new empty database).
    info(f"Starting {service} fresh...")
    started = do_up(service, env, profile, fresh=True)
    if kept:
        info(f"  undo with: uv run homeserver.py {env} restore {service} --snapshot {kept.name}")
    return started


def do_dump(service: str, env: str, profile: str | None) -> bool:
    """Logical pg_dump of <service>-db into service_data/db_dump/<service>/<ts>/
    — the source dump 'migrate' restores from for a Debian->Alpine (or any
    other Postgres image) migration. Requires the DB container running."""
    ext = shared_db_external(service)
    if ext:
        error(f"{service}'s database is on outside host {ext} (DB_HOST) — dump it with that provider's tools (pg_dump/mariadb-dump against {ext})")
        return False
    c = shared_db_creds(service)
    if c:
        if BACKEND.container_status(c["container"]) != "running":
            error(f"{c['container']} is not running — start {service} first")
            return False
        ts = time.strftime("%Y%m%d-%H%M%S")
        dump_dir = DB_DUMP_ROOT / service / ts
        dump_dir.mkdir(parents=True, exist_ok=True)
        info(f"Dumping {service}'s database(s) from {c['container']} -> service_data/db_dump/{service}/{ts}/")
        # No roles file: the app's role is recreated from its .env by
        # provision_shared_db, and a --roles-only dump of a shared server
        # would carry every other app's role and password with it.
        return dump_shared_db(service, dump_dir, ts) is not None

    db_container = f"{service}-db"
    if BACKEND.container_status(db_container) != "running":
        error(f"{db_container} is not running — start {service} first")
        return False

    service_env = load_env_file(SERVICES_DIR / service / ".env")
    user = service_env.get("POSTGRES_USER")
    db = service_env.get("POSTGRES_DB")
    if not user or not db:
        error(f"services/{service}/.env has no POSTGRES_USER/POSTGRES_DB — not a standard Postgres service")
        return False

    ts = time.strftime("%Y%m%d-%H%M%S")
    dump_dir = DB_DUMP_ROOT / service / ts
    dump_dir.mkdir(parents=True, exist_ok=True)
    # Timestamp in the filename too (not just the parent dir) — same
    # reasoning as backup_service, so the file keeps its identity if ever
    # copied out of its dump folder.
    fname = f"{service}_{ts}.dump"
    dump_file = dump_dir / fname

    info(f"Dumping {db_container} ({user}/{db}) -> service_data/db_dump/{service}/{ts}/{fname}")
    ok, data, err = BACKEND.db_pg_dump(db_container, user, db)
    if not ok:
        error(f"  pg_dump failed: {err}")
        return False

    dump_file.write_bytes(data)
    success(f"  dumped {len(data):,} bytes")

    # Roles are cluster-wide, not captured by the per-database dump above —
    # an app can authenticate as a role that isn't POSTGRES_USER (e.g. one
    # created ad-hoc during its own first-run setup, like Nextcloud's
    # 'oc_admin'), and without this that role silently never gets recreated
    # in a migrated/restored cluster. Best-effort: don't fail the whole dump
    # if this one part doesn't work, since pg_dump above already succeeded.
    roles_ok, roles_data, roles_err = BACKEND.db_pg_dumpall_roles(db_container, user)
    if roles_ok:
        roles_file = dump_dir / f"{service}_roles_{ts}.sql"
        roles_file.write_bytes(roles_data)
        success(f"  dumped roles ({len(roles_data):,} bytes)")
    else:
        warn(f"  pg_dumpall --roles-only failed (continuing without it): {roles_err}")

    return True


def do_migrate(service: str, env: str, profile: str | None, image_override: str | None = None) -> bool:
    """Migrate <service>-db to a different Postgres image using the latest
    dump from 'dump' — never reuses the old volume's data files directly
    (glibc/musl collation mismatch risk), see homeserver-postgres skill.
    Stops the service, swaps compose.yml's image tag and renames the
    postgres volume, starts the DB alone on a fresh volume, restores the
    dump into it, then brings the rest of the service back up. Leaves the
    old volume in place — remove it manually once you've verified this
    worked (see the message printed at the end).

    image_override (--image): explicit target tag or full 'repo:tag'. Without
    it, the image line must be the plain official 'postgres:<tag>' (no
    registry/path prefix) and the default transform is appending '-alpine'.
    A prefixed image (a custom/extended build, e.g. immich's vectorchord/
    pgvector fork) is never auto-inferred — there's no way to know whether
    that specific fork even publishes an alpine (or any other) variant, so
    --image is required for those."""
    if shared_db_creds(service):
        error(f"{service} keeps its database on {shared_db_creds(service)['container']} — migrate only handles a per-service <service>-db container")
        return False
    dumps = list_dumps(service)
    if not dumps:
        error(f"No dump found for {service} — run 'dump {service}' first")
        return False
    dump_files = sorted(dumps[-1].glob("*.dump"))
    if not dump_files:
        error(f"Dump file missing in {dumps[-1]}")
        return False
    dump_file = dump_files[0]

    compose_path = SERVICES_DIR / service / "compose.yml"
    if not compose_path.is_file():
        error(f"{compose_path} not found")
        return False
    text = compose_path.read_text(encoding="utf-8")

    # Captures an optional registry/path prefix separately from the bare
    # "postgres" repo name, so the plain official image (no prefix) and a
    # custom/extended fork (any prefix) can be told apart and handled
    # differently — see image_override docs above.
    m = re.search(r"image:\s*((?:[\w./-]+/)?postgres):([\w.-]+)\n", text)
    if not m:
        error(f"No '.../postgres:<tag>' image line found in {service}/compose.yml — not a Postgres service")
        return False
    repo, tag = m.group(1), m.group(2)
    old_full = f"{repo}:{tag}"

    if image_override:
        new_full = image_override if ":" in image_override else f"{repo}:{image_override}"
        if new_full == old_full:
            error(f"{service}-db is already on {old_full}")
            return False
        new_tag = new_full.split(":", 1)[1]  # only used for the volume-name suffix below
    elif repo != "postgres":
        error(
            f"{service}-db uses a custom Postgres image ({old_full}) — auto '-alpine' inference only "
            "applies to the plain official image. Specify the target explicitly: --image <repo:tag>"
        )
        return False
    elif tag.endswith("-alpine"):
        error(f"{service}-db is already on an alpine tag ({old_full}) — pass --image for a different target")
        return False
    else:
        new_tag = f"{tag}-alpine"
        new_full = f"{repo}:{new_tag}"

    vol_m = re.search(r"-\s*([\w-]+):/var/lib/postgresql\b", text)
    if not vol_m:
        error(f"Could not find the Postgres volume mount (:/var/lib/postgresql) in {service}/compose.yml")
        return False
    old_vol = vol_m.group(1)
    # Keep the plain '-alpine' suffix for the default case (matches the
    # already-established naming on forgejo/guacamole/nextcloud); a custom
    # --image target gets its sanitized tag as the suffix instead, since
    # 'alpine' alone wouldn't mean anything for e.g. a version bump.
    vol_suffix = "alpine" if new_tag == f"{tag}-alpine" else re.sub(r"[^a-zA-Z0-9]+", "-", new_tag).strip("-")
    new_vol = f"{old_vol}-{vol_suffix}"

    service_env = load_env_file(SERVICES_DIR / service / ".env")
    user = service_env.get("POSTGRES_USER")
    db = service_env.get("POSTGRES_DB")
    if not user or not db:
        error(f"services/{service}/.env has no POSTGRES_USER/POSTGRES_DB")
        return False

    info(f"Migrating {service}-db: {old_full} -> {new_full} (volume {old_vol} -> {new_vol})")

    was_running = service in get_running_services()
    do_down(service, env, profile, no_backup=False)

    # Two targeted, anchored substitutions rather than a blanket rename of
    # every occurrence of old_vol — avoids accidentally touching another
    # volume name that happens to share old_vol as a prefix.
    new_text = text.replace(f"image: {old_full}", f"image: {new_full}", 1)
    new_text, n1 = re.subn(
        rf"^(\s*-\s*){re.escape(old_vol)}(:/var/lib/postgresql\b)", rf"\g<1>{new_vol}\g<2>",
        new_text, count=1, flags=re.MULTILINE,
    )
    new_text, n2 = re.subn(
        rf"^(\s*){re.escape(old_vol)}(:\s*)$", rf"\g<1>{new_vol}\g<2>",
        new_text, count=1, flags=re.MULTILINE,
    )
    if n1 == 0 or n2 == 0:
        error(f"Couldn't safely rename volume '{old_vol}' in compose.yml (mount line found: {bool(n1)}, declaration found: {bool(n2)}) — aborting before writing anything")
        return False
    compose_path.write_text(new_text, encoding="utf-8")

    files = compose_files(service, env)
    cenv = compose_env(service)
    db_container = f"{service}-db"

    info(f"Starting fresh {db_container} on the new volume...")
    ok, out = BACKEND.compose_up(files, cenv, None, only=[db_container])
    if not ok:
        error(f"  failed to start {db_container}: {out}")
        return False
    if not wait_container_healthy(db_container):
        error(f"  {db_container} did not become healthy on the fresh volume")
        return False

    # Apply the roles dump (if 'dump' captured one) before the main restore,
    # so any role the app authenticates as beyond POSTGRES_USER (e.g.
    # Nextcloud's ad-hoc 'oc_admin') exists before the app ever tries to
    # connect. Best-effort — older dumps predating this fix won't have one.
    roles_files = sorted(dumps[-1].glob("*_roles_*.sql"))
    if roles_files:
        info(f"Applying roles from {roles_files[0].name}...")
        ok, err = BACKEND.db_psql_apply(db_container, user, db, roles_files[0].read_bytes())
        if not ok:
            warn(f"  applying roles had issues (continuing — 'role already exists' for POSTGRES_USER/postgres is expected): {err}")
        else:
            success("  roles applied")

    info(f"Restoring {dump_file.parent.name} into {db_container}...")
    ok, err = BACKEND.db_pg_restore(db_container, user, db, dump_file.read_bytes())
    if not ok:
        error(f"  pg_restore failed: {err}")
        return False
    success("  restore complete")

    up_ok = True
    if was_running:
        up_ok = do_up(service, env, profile)
        if not up_ok:
            error(f"  restore succeeded but bringing {service} back up failed — the DB has your data, but check `dev logs {service}` and re-run `dev up {service}` yourself")

    old_full_vol = f"{service}_{old_vol}"
    warn(
        f"Old volume '{old_full_vol}' left in place — verify {service} actually works "
        f"(not just that it started), then remove it: docker volume rm {old_full_vol}"
    )
    return up_ok


def do_logs(service: str, env: str) -> None:
    d = SERVICES_DIR / service
    if not d.is_dir():
        error(f"Service '{service}' not found")
        return

    files = compose_files(service, env)
    cenv = compose_env(service)
    BACKEND.compose_logs_follow(files, cenv)


# ── Disk reclaim (gc) ───────────────────────────────────────────────
#
# Pruning alone (docker system/builder prune) only frees space *inside*
# Docker Desktop's WSL2 VHDX — the .vhdx file on disk never shrinks on its
# own no matter how much you delete inside it. Actually reclaiming that disk
# space needs fstrim (tell the WSL2 VM's filesystem which blocks are free)
# + wsl --shutdown + a diskpart compact pass. See
# docs/08-maintenance.md#reclaiming-disk-space-docker-desktop-on-windows--wsl2
# for the manual version of this procedure this automates.


def _is_windows_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes  # noqa: PLC0415
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _find_docker_vhdx() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    # Path/filename depends on Docker Desktop version — try newer first.
    candidates = [
        Path(local) / "Docker" / "wsl" / "disk" / "docker_data.vhdx",
        Path(local) / "Docker" / "wsl" / "data" / "ext4.vhdx",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _gb(n: int) -> float:
    return n / (1024 ** 3)


def _compact_docker_vhdx(vhdx: Path) -> None:
    if not _is_windows_admin():
        warn("Not running as Administrator — diskpart compaction needs elevation")
        warn(f"  (it silently no-ops otherwise). Re-run from an Administrator terminal to compact {vhdx}")
        return

    before = vhdx.stat().st_size
    info("Trimming filesystem inside the WSL2 VM...")
    subprocess.run(["wsl", "-d", "docker-desktop", "-u", "root", "--", "fstrim", "-av"])
    info("Shutting down WSL...")
    subprocess.run(["wsl", "--shutdown"])
    info("Compacting VHDX via diskpart (this can take a minute)...")
    script = f'select vdisk file="{vhdx}"\nattach vdisk readonly\ncompact vdisk\ndetach vdisk\nexit\n'
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(script)
        script_path = f.name
    try:
        subprocess.run(["diskpart", "/s", script_path])
    finally:
        os.unlink(script_path)

    after = vhdx.stat().st_size
    reclaimed = _gb(before - after)
    if reclaimed > 0.05:
        success(f"VHDX compacted: {_gb(before):.2f}GB -> {_gb(after):.2f}GB (reclaimed {reclaimed:.2f}GB)")
    else:
        warn(f"VHDX barely shrank ({_gb(before):.2f}GB -> {_gb(after):.2f}GB)")
        warn("  If this persists, try the export/reimport procedure in docs/08-maintenance.md")


# ── Archive: everything git doesn't hold, in one verified file ──────
#
# `archive <dest-dir>` packs what a fresh clone of this repo can't recreate:
# every git-ignored file in the repo (all .env secrets, local-only notes),
# service_data/ (snapshots — the only copy of the databases, which are named
# Docker volumes — plus live data and db dumps), and a git bundle of the repo
# itself so unpushed commits survive too. Regenerable things are left out.

ARCHIVE_SKIP_IGNORED = ("service_data", ".venv/", "__pycache__/", ".pytest_cache/", ".ruff_cache/", "node_modules/")
ARCHIVE_EXCLUDES = ["service_data/cache", "*/__pycache__"]


def archive_ignored_paths() -> list[str]:
    """Git-ignored/untracked paths in the repo (directories collapsed), minus
    regenerable ones and service_data (archived separately, from its real
    location). Asks git, so new ignored files are covered automatically."""
    proc = subprocess.run(
        ["git", "-C", str(BASE_DIR), "ls-files", "--others", "--ignored", "--exclude-standard", "--directory"],
        capture_output=True, text=True,
    )
    paths = []
    for line in proc.stdout.splitlines():
        if not line or any(line == skip.rstrip("/") or line.startswith(skip) or f"/{skip}" in f"/{line}" for skip in ARCHIVE_SKIP_IGNORED):
            continue
        paths.append(line.rstrip("/"))
    # Drop entries already covered by a listed parent directory (git lists
    # e.g. both services/photoprism and services/photoprism/.env), so no file
    # lands in the archive twice.
    paths = sorted(set(paths))
    return [p for p in paths if not any(p.startswith(q + "/") for q in paths if q != p)]


def archive_meta(meta_dir: Path, running: list[str]) -> None:
    """README, MANIFEST and a git bundle, written into meta_dir."""
    git = lambda *a: subprocess.run(["git", "-C", str(BASE_DIR), *a], capture_output=True, text=True).stdout.strip()  # noqa: E731
    subprocess.run(["git", "-C", str(BASE_DIR), "bundle", "create", str(meta_dir / "homeserver.bundle"), "--all"], capture_output=True)
    lines = [
        f"created: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"git: branch {git('rev-parse', '--abbrev-ref', 'HEAD')} at {git('rev-parse', 'HEAD')}",
        f"running when archived: {', '.join(running) or 'none'}",
        "",
        "latest snapshot per service:",
    ]
    for d in sorted(p for p in BACKUP_ROOT.iterdir() if p.is_dir()) if BACKUP_ROOT.is_dir() else []:
        snaps = list_snapshots(d.name)
        resets = list_reset_backups(d.name)
        lines.append(f"  {d.name}: {snaps[-1].name if snaps else '-'}" + (f"  (+{len(resets)} reset-backup)" if resets else ""))
    (meta_dir / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    (meta_dir / "README.txt").write_text(
        "homeserver archive\n\n"
        "homeserver/      every git-ignored file of the repo (.env secrets, local notes)\n"
        "service_data/    snapshots (incl. databases), live data, db dumps — not cache/\n"
        "meta/homeserver.bundle   the git repo, incl. unpushed commits\n\n"
        "Restore on a new machine (Docker, git and uv installed; see docs/08-maintenance.md):\n"
        "  sha256sum -c <archive>.tar.gz.sha256\n"
        "  sudo tar --numeric-owner -xpzf <archive>.tar.gz -C <staging dir>\n"
        "      (as root, numerically: files belong to app uids like 472 or 10001)\n"
        "  git clone <staging>/meta/homeserver.bundle homeserver\n"
        "  git -C homeserver checkout <branch from MANIFEST.txt>\n"
        "  cp -a <staging>/homeserver/. homeserver/   ('/.', not '/*': .env is a dotfile)\n"
        "  sudo mv <staging>/service_data <data drive>/service_data\n"
        "  ln -s <data drive>/service_data homeserver/service_data\n"
        "  edit homeserver/.env for this machine (RUNTIME, DOCKER_SOCKET), then:\n"
        "  uv run homeserver.py prod restore all -y   (volumes and databases from snapshots)\n"
        "  uv run homeserver.py prod up all\n"
        "Not included: media under /mnt/media (Immich photos, Nextcloud user files,\n"
        "Jellyfin library), service_data/cache, .venv — all regenerable or separate.\n"
    )


def archive_verify(archive: Path) -> tuple[bool, str]:
    """Read the whole archive back (which also validates gzip) and check the
    three top-level parts are inside. Returns (ok, top-level names found)."""
    proc = subprocess.run(["tar", "-tzf", str(archive)], capture_output=True, text=True)
    tops = sorted({line.split("/", 1)[0] for line in proc.stdout.splitlines() if line})
    ok = proc.returncode == 0 and {"homeserver", "service_data", "meta"} <= set(tops)
    return ok, ", ".join(tops)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda e: None):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def do_archive(dest: str) -> int:
    dest_dir = Path(dest).expanduser()
    if not dest_dir.is_dir():
        error(f"{dest_dir} doesn't exist — create it (or mount the drive) first")
        return 1

    running = get_running_services()
    if running:
        warn(f"Running now: {', '.join(running)}")
        warn("  their live service_data/data may be mid-write; snapshots are always consistent.")
        warn("  For a fully consistent archive: 'down all' (or 'backup <service>') first.")

    data_real = (BASE_DIR / "service_data").resolve()
    needed = tree_size(data_real) - tree_size(data_real / "cache")
    free = shutil.disk_usage(dest_dir).free
    if free < needed:
        error(f"Not enough space in {dest_dir}: need up to {needed / 1e9:.1f} GB, {free / 1e9:.1f} GB free")
        return 1

    ts = time.strftime("%Y%m%d-%H%M%S")
    out = dest_dir / f"homeserver-archive-{ts}.tar.gz"
    ignored = archive_ignored_paths()
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp)
        archive_meta(meta, running)
        header(f"Archiving to {out}")
        info(f"{len(ignored)} git-ignored path(s) from the repo, service_data (minus cache), meta (README, MANIFEST, git bundle)...")
        ok, err = BACKEND.archive_paths(
            {BASE_DIR: "homeserver", data_real: "service_data", meta: "meta"},
            [f"homeserver/{p}" for p in ignored] + ["service_data", "meta"],
            ARCHIVE_EXCLUDES,
            out,
        )
    if not ok:
        error(f"Archive failed: {err.strip()[-400:]}")
        return 1

    info("Verifying (reading the whole archive back)...")
    ok, tops = archive_verify(out)
    if not ok:
        error(f"Verification failed — archive is incomplete or unreadable (found: {tops})")
        return 1
    digest = file_sha256(out)
    (dest_dir / f"{out.name}.sha256").write_text(f"{digest}  {out.name}\n")
    success(f"{out} ({out.stat().st_size / 1e9:.1f} GB) verified: {tops}")
    success(f"checksum: {out.name}.sha256 — check later with: sha256sum -c {out.name}.sha256")
    return 0


def do_gc(assume_yes: bool = False) -> int:
    header(f"Reclaiming Docker disk space (runtime: {RUNTIME})...")

    warn("This prunes ALL unused images/containers/volumes on this Docker host —")
    warn("not just this stack's. If other projects share this Docker install, their")
    warn("unused resources get pruned too.")
    if sys.platform == "win32":
        vhdx = _find_docker_vhdx()
        if vhdx:
            warn(f"It will also shut down WSL and compact {vhdx.name} via diskpart.")
    if not assume_yes:
        try:
            reply = input(f"\n{BOLD}Continue? [y/N]{RESET} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            info("Cancelled")
            return 1
        if reply not in ("y", "yes"):
            info("Cancelled")
            return 1
    print()

    info("Pruning unused images, containers, and volumes...")
    ok, out = BACKEND.system_prune()
    if out.strip():
        print(out.strip())
    success("System prune complete") if ok else error("System prune failed")

    info("Pruning build cache...")
    ok2, out2 = BACKEND.builder_prune()
    if out2.strip():
        print(out2.strip())
    success("Builder prune complete") if ok2 else error("Builder prune failed")

    if sys.platform == "win32":
        vhdx = _find_docker_vhdx()
        if vhdx:
            _compact_docker_vhdx(vhdx)
        else:
            info("No Docker Desktop WSL2 VHDX found — nothing more to reclaim")
    else:
        info("Native Docker frees space on the host filesystem immediately — prune above is the whole story here")

    print(f"\n{BOLD}{'━' * 40}{RESET}")
    success("Done")
    print(f"{BOLD}{'━' * 40}{RESET}\n")
    return 0


def do_orphaned_volumes(target: str, assume_yes: bool) -> int:
    """List (and optionally remove) Docker volumes matching <service>_* that
    exist but aren't declared in that service's current compose.yml —
    automates what backup_service()'s warning flags one service at a time.
    """
    header("Checking for orphaned Docker volumes...")

    if target == "all":
        services = (
            SERVICES_MIN
            + SERVICES_CORE
            + SERVICES_DAILY
            + SERVICES_BROWSER
            + SERVICES_OFFICE
            + SERVICES_AUTOMATION_AI
            + SERVICES_EXTRA
            + SERVICES_MANUAL
        )
    else:
        if not is_valid_service(target):
            error(f"Service '{target}' not found")
            return 1
        services = [target]

    found: list[str] = []
    for s in services:
        for v in find_orphaned_volumes(s):
            warn(f"{v}  (service: {s}, not declared in services/{s}/{base_file(s)})")
            found.append(v)

    if not found:
        success("No orphaned volumes found")
        return 0

    print()
    warn(f"{len(found)} orphaned volume(s) found above.")
    warn("Check you don't need old data in one before removing, e.g.:")
    warn("  docker run --rm -v <volume>:/data alpine ls -la /data")

    if not assume_yes:
        try:
            reply = input(f"\n{BOLD}Remove all {len(found)} listed above? [y/N]{RESET} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            info("Cancelled")
            return 1
        if reply not in ("y", "yes"):
            info("Cancelled — nothing removed")
            return 0

    print()
    ok = True
    for v in found:
        if BACKEND.volume_remove(v):
            success(f"Removed {v}")
        else:
            error(f"Failed to remove {v}")
            ok = False
    return 0 if ok else 1


def find_stale_network_containers() -> list[dict]:
    """Running containers whose HostConfig.NetworkMode names a real network
    (not host/none/container:<id>) but whose NetworkSettings.Networks is
    currently empty — a detached/orphaned network endpoint. The container's
    own process never notices (it keeps running, even reporting healthy on
    its own localhost-only healthcheck) but nothing else can reach it, and
    anything it depends on for its own outbound connections (e.g. atuin ->
    atuin-db) fails DNS resolution outright. Hit on this stack right after
    the 'homeserver' network was recreated during the 2026-09-04
    IPv6-lockdown work (docs/09-firewall.md) — atuin, then separately
    jellyfin/guacamole/it-tools/mailpit, were all left in this state. A
    plain `docker restart` does NOT fix it (confirmed against atuin): restart
    reuses the same stale endpoint. Only a full recreate rebuilds it, which
    is what do_fix_network does below."""
    stale = []
    for name in BACKEND.running_container_names():
        info = BACKEND.container_info(name)
        if not info:
            continue
        mode = info.get("network_mode", "")
        if not mode or mode in ("host", "none") or mode.startswith("container:"):
            continue
        if info.get("networks"):
            continue
        stale.append({"container": name, **info})
    return stale


def do_fix_network(assume_yes: bool) -> int:
    """Detect and repair containers stuck with a detached network endpoint
    (see find_stale_network_containers) by recreating just the affected
    container(s) — via the same compose project/service/files each was
    originally started with, read back off its own Docker labels, so this
    needs no <env> argument and never touches anything else in the
    project. Bind mounts and named volumes are untouched by a recreate."""
    header("Checking for containers detached from their Docker network...")
    stale = find_stale_network_containers()
    if not stale:
        success("No stale network attachments found")
        return 0

    for s in stale:
        warn(f"{s['container']}  (service: {s.get('compose_project') or '?'}, network mode: {s.get('network_mode')})")

    print()
    warn(f"{len(stale)} container(s) found above with no live network endpoint.")
    warn("A plain restart will NOT fix this — each will be force-recreated (bind mounts/volumes untouched).")

    if not assume_yes:
        try:
            reply = input(f"\n{BOLD}Recreate all {len(stale)} listed above? [y/N]{RESET} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print()
            info("Cancelled")
            return 1
        if reply not in ("y", "yes"):
            info("Cancelled — nothing recreated")
            return 0

    print()
    ok = True
    for s in stale:
        container = s["container"]
        service = s.get("compose_project", "")
        compose_service = s.get("compose_service", "")
        config_files = s.get("config_files") or []
        if not service or not is_valid_service(service):
            error(f"  {container}: unknown/missing compose project label — recreate it manually")
            ok = False
            continue
        if any("compose.prod.yml" in f for f in config_files):
            env = "prod"
        elif any("compose.dev.yml" in f for f in config_files):
            env = "dev"
        else:
            error(f"  {container}: can't tell dev/prod from its recorded compose files — recreate it manually")
            ok = False
            continue
        recreated, output = BACKEND.compose_up(
            compose_files(service, env), compose_env(service), None,
            force_recreate=True, only=[compose_service] if compose_service else None,
        )
        if recreated:
            success(f"Recreated {container} ({service}, {env})")
        else:
            error(f"  Failed to recreate {container}: {output.strip()[-300:]}")
            ok = False
    return 0 if ok else 1


# ── Help ─────────────────────────────────────────────────────────────


def show_help() -> None:
    print()
    print(f"{BOLD}  homeserver.py — manage homeserver services (runtime: {RUNTIME}){RESET}")
    print()
    print(f"  {BOLD}Usage:{RESET}")
    print("    python homeserver.py <env> <up|down|restart|logs|update> <tier|service...> [--profile <name>]")
    print("    python homeserver.py <env> -u <service...>                     (up shorthand)")
    print("    python homeserver.py <env> -d <service...>                     (down shorthand)")
    print("    python homeserver.py <env> -r <service...>                     (restart shorthand)")
    print("    python homeserver.py <env> precreate <tier|service...> [--update]  create without starting (visible in Portainer);")
    print("                                                                     --update force-recreates existing (not running) containers")
    print("    python homeserver.py gc [--yes]                                 reclaim Docker disk space")
    print("    python homeserver.py orphaned-volumes [service|all] [--yes]     list/remove volumes not in current compose.yml")
    print("    python homeserver.py status (or ps)                             list every service + every group (tier by tier, marking which are running)")
    print("    python homeserver.py fix-network [--yes]                        recreate any running container detached from the 'homeserver' network")
    print()
    print(f"  {BOLD}Environments:{RESET}")
    print("    dev    ports on all interfaces (direct access)")
    print("    prod   ports on 127.0.0.1 only (nginx proxy handles external)")
    print()
    print(f"  {BOLD}Tiers:{RESET}")
    print("    min     bare minimum — beszel, cloudflared, nginx-plain, landing, docs, portainer")
    print("    core    full default stack — 'up core' bootstraps min if not already running;")
    print("            'down core' stops only core, min stays up")
    print("    daily   apps used regularly but not core infra — opt-in, NOT included by 'core';")
    print("            'up daily' bootstraps min/core if needed; 'down daily' stops only daily")
    print("    browser the Browser Hub's remote browsers — opt-in; 'up browser' bootstraps min/core/daily if needed;")
    print("            'down browser' stops only the browsers")
    print("    office  firm/business apps — opt-in; 'up office' bootstraps min/core/daily/browser if needed;")
    print("            'down office' stops only office")
    print("    automation-ai workflow/automation/AI apps — opt-in; 'up automation-ai' bootstraps")
    print("            min/core/daily/browser/office if needed; 'down automation-ai' stops only automation-ai")
    print("    extra   everything else (observability, paperless, erpnext, ...) — opt-in; 'up extra' bootstraps")
    print("            min/core/daily/browser/office/automation-ai if needed; 'down extra' stops only extra")
    print("    all     core + daily + browser + office + automation-ai + extra — starts/stops literally everything")
    print("    running update only — currently running services")
    print()
    print(f"  {BOLD}Groups:{RESET}")
    print("    group:<name>  every service in category/subcategory <name> — works with any action")
    print(f"    valid names: {', '.join(sorted(SERVICE_GROUPS))}")
    print()
    print(f"  {BOLD}Examples:{RESET}")
    print("    python homeserver.py dev up min                      start bare minimum")
    print("    python homeserver.py dev up core                     start full default stack")
    print("    python homeserver.py dev up daily                    start core + the daily-use opt-in tier")
    print("    python homeserver.py dev up browser                  start core + daily + the Browser Hub's browsers")
    print("    python homeserver.py dev up office                   start core + daily + browser + the firm/business opt-in tier")
    print("    python homeserver.py dev up automation-ai            start core + daily + browser + office + the automation/AI opt-in tier")
    print("    python homeserver.py dev up extra                    start everything below 'all' plus the extra opt-in tier (bootstraps lower tiers)")
    print("    python homeserver.py dev up all                      start everything (core + daily + browser + office + automation-ai + extra)")
    print("    python homeserver.py dev down min                    stop minimum (reverse order)")
    print("    python homeserver.py dev down core                   stop core only, reverse order (min stays up)")
    print("    python homeserver.py dev down daily                  stop daily only, reverse order (min/core stay up)")
    print("    python homeserver.py dev down all                    stop everything, including optional profiles (reverse order)")
    print("    python homeserver.py dev up all --yes                start everything, skip the confirmation prompt")
    print("    python homeserver.py dev up landing mealie           start specific services")
    print("    python homeserver.py dev down landing mealie         stop specific services")
    print("    python homeserver.py dev up forgejo                   start Forgejo and its CI runner")
    print("    python homeserver.py dev down forgejo                 stop Forgejo and every optional profile")
    print("    python homeserver.py dev restart nginx-plain         restart a service (re-runs entrypoint)")
    print("    python homeserver.py dev -r nginx-plain              same, shorthand")
    print("    python homeserver.py dev logs immich                 follow logs")
    print("    python homeserver.py dev update all                  pull latest and recreate all")
    print("    python homeserver.py dev update running              update only currently running")
    print("    python homeserver.py dev update jellyfin             update a single service")
    print("    python homeserver.py dev down mealie                 stop AND auto-snapshot (default)")
    print("    python homeserver.py dev down mealie --no-backup     stop without snapshotting")
    print("    python homeserver.py dev up mealie                   auto-restores the latest snapshot if data/volumes are missing")
    print("    python homeserver.py dev up mealie --fresh           start blank even if a snapshot exists")
    print("    python homeserver.py dev reset mealie                snapshot, wipe and start blank (restore undoes it)")
    print("    python homeserver.py archive /run/media/<you>/Drive   everything git doesn't hold, in one verified tar.gz")
    print("    python homeserver.py dev up immich --no-ml           start immich without the ML container")
    print("    python homeserver.py prod up adguard-home --no-wg    don't start wg-easy first (it stays as it is)")
    print("    python homeserver.py dev up group:notes              start every note-taking app (category/subcategory group)")
    print("    python homeserver.py dev down group:notes            stop the same group")
    print("    python homeserver.py dev precreate all gitlab stirling-pdf")
    print("                                                         create every never-started service (incl. manual-tier) so")
    print("                                                         they all show up as start-able stacks in Portainer")
    print("    python homeserver.py dev precreate daily --update    rebuild daily-tier containers with the current .env (skips any that are running)")
    print("    python homeserver.py dev backup all                  snapshot every service now, regardless of running state")
    print("    python homeserver.py dev snapshots mealie            list available snapshots for a service")
    print("    python homeserver.py dev restore mealie              restore the latest snapshot")
    print("    python homeserver.py dev restore mealie --snapshot 20260710-160628")
    print("                                                         restore a specific snapshot")
    print("    python homeserver.py dev dump forgejo                logical pg_dump -> service_data/db_dump/forgejo/<ts>/")
    print("    python homeserver.py dev migrate forgejo             migrate forgejo-db to postgres-alpine using the latest dump")
    print("    python homeserver.py dev migrate immich --image ghcr.io/immich-app/postgres:18-vectorchord0.6.0-pgvector0.9.0")
    print("                                                         explicit target — required for non-official Postgres images")
    print("    python homeserver.py gc                              prune + (Windows) compact Docker Desktop's WSL2 VHDX")
    print("    python homeserver.py gc --yes                        same, skip the confirmation prompt")
    print("    python homeserver.py status                          list every service + every group, marking which are running")
    print("    python homeserver.py fix-network                     recreate any container detached from the 'homeserver' network")
    print("    python homeserver.py fix-network --yes                same, skip the confirmation prompt")
    print()
    print(f"  {BOLD}MIN (infrastructure):{RESET}")
    print(f"    {' '.join(SERVICES_MIN)}")
    print()
    print(f"  {BOLD}CORE (always-on apps, added on top of min):{RESET}")
    print(f"    {' '.join(SERVICES_CORE)}")
    print()
    print(f"  {BOLD}DAILY (regular-use apps, opt-in — 'up daily' or 'up all', NOT 'up core'):{RESET}")
    print(f"    {' '.join(SERVICES_DAILY)}")
    print()
    print(f"  {BOLD}BROWSER (Browser Hub's remote browsers, opt-in — 'up browser' or 'up all', NOT 'up daily'):{RESET}")
    print(f"    {' '.join(SERVICES_BROWSER)}")
    print()
    print(f"  {BOLD}OFFICE (firm/business apps, opt-in — 'up office' or 'up all', NOT 'up browser'):{RESET}")
    print(f"    {' '.join(SERVICES_OFFICE)}")
    print()
    print(f"  {BOLD}AUTOMATION-AI (workflow/automation/AI apps, opt-in — 'up automation-ai' or 'up all', NOT 'up office'):{RESET}")
    print(f"    {' '.join(SERVICES_AUTOMATION_AI)}")
    print()
    print(f"  {BOLD}EXTRA (optional, opt-in — 'up extra' or 'up all', NOT 'up automation-ai'):{RESET}")
    print(f"    {' '.join(SERVICES_EXTRA)}")
    print()
    print(f"  {BOLD}MANUAL (never auto-started — start individually):{RESET}")
    print(f"    {' '.join(SERVICES_MANUAL)}")
    print()
    print(f"  {BOLD}PROXY (manual-only — never auto-started, mutex with nginx-plain):{RESET}")
    print(f"    {PROXY_STANDBY}")
    print()
    print(f"  {BOLD}Health timeout:{RESET} {HEALTH_TIMEOUT}s per service")
    print()


# ── Execute ──────────────────────────────────────────────────────────


# The 'homeserver' network's subnet is pinned, never left to Docker. The browser containers have fixed IPs
# inside it (ipv4_address in services/<browser>/compose.yml, and the LAN-isolation rules in
# services/nginx-plain/browser-lan-block.sh); when the network was recreated without a subnet on 2026-10-05,
# Docker picked 172.19.0.0/16 instead of 172.18.0.0/16 and every browser failed to create with "no configured
# subnet contains IP address". tests/test_repo_invariants.py checks those IPs are inside this subnet.
HOMESERVER_SUBNET = "172.19.0.0/16"


def ensure_network() -> None:
    if not BACKEND.network_exists("homeserver"):
        warn("Network 'homeserver' not found — creating...")
        BACKEND.network_create("homeserver", HOMESERVER_SUBNET)
        success(f"Network 'homeserver' created ({HOMESERVER_SUBNET})")
    else:
        have = BACKEND.network_subnets("homeserver")
        if have and HOMESERVER_SUBNET not in have:
            warn(f"Network 'homeserver' is on {', '.join(have)}, not {HOMESERVER_SUBNET}: containers with a fixed IP "
                 f"(the Browser Hub) will fail to create. Recreate the network on that subnet, or change HOMESERVER_SUBNET "
                 f"and the browsers' IPs together (docs/02-docker-network.md).")


def confirm_expansion(services: list[str], assume_yes: bool) -> bool:
    """Preview + confirm before acting on a tier keyword (min/core/daily/all/
    running) or a group:<name>/bundle expansion — anything where one token
    resolved into more than what was literally typed. Never called for a
    literal list of explicitly-named services (see the call sites in main()):
    that case needs no prompt since the user already named exactly what they
    want. Skipped when --yes/-y was passed, or stdin isn't a TTY (scripted/
    cron usage must never hang on an unanswerable prompt) — same pattern as
    do_gc/do_orphaned_volumes' assume_yes."""
    if assume_yes or not sys.stdin.isatty():
        return True
    print(f"\n{BOLD}This will affect {len(services)} service(s):{RESET}")
    print(f"  {' '.join(services)}")
    try:
        reply = input(f"\n{BOLD}Continue? [y/N]{RESET} ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        info("Cancelled")
        return False
    if reply not in ("y", "yes"):
        info("Cancelled")
        return False
    return True


def run_list(action_fn, services: list[str], env: str, profile: str | None, label: str, **kwargs) -> None:
    failed: list[str] = []
    for service in services:
        ok = action_fn(service, env, profile, **kwargs)
        if not ok:
            error(f"{service} FAILED")
            failed.append(service)
        else:
            if action_fn is do_up:
                success(f"{service} started")
            elif action_fn is do_precreate:
                success(f"{service} pre-created")
            elif action_fn is do_update:
                success(f"{service} updated")
            elif action_fn is do_backup:
                success(f"{service} backed up")
            elif action_fn is do_restore:
                success(f"{service} restored")
            elif action_fn is do_dump:
                success(f"{service} dumped")
            elif action_fn is do_migrate:
                success(f"{service} migrated")
            elif action_fn is do_reset:
                success(f"{service} reset — fresh start")
        print()

    print(f"{BOLD}{'━' * 40}{RESET}")
    if not failed:
        success(f"{label} completed successfully")
    else:
        warn("Completed with failures:")
        for f in failed:
            error(f"  {f}")
        print(f"\n  Run {CYAN}python homeserver.py {env} logs <service>{RESET} to investigate")
    print(f"{BOLD}{'━' * 40}{RESET}\n")


def main() -> int:
    global NO_WG_START
    argv = sys.argv[1:]

    # Standalone verb, not part of the <env> <action> <target> pattern below —
    # disk reclaim isn't env/service-scoped, it's a whole-Docker-host operation.
    if argv and argv[0] == "gc":
        return do_gc(assume_yes="--yes" in argv or "-y" in argv)

    # Same reasoning — a volume either exists on this host or it doesn't,
    # dev/prod doesn't change that.
    if argv and argv[0] == "orphaned-volumes":
        target = next((a for a in argv[1:] if not a.startswith("-")), "all")
        return do_orphaned_volumes(target, assume_yes="--yes" in argv or "-y" in argv)

    # Same reasoning — which containers are running doesn't depend on
    # dev/prod (only the port bindings do), so this needs no env argument.
    if argv and argv[0] in ("status", "ps"):
        return do_status()

    # Same reasoning again — each affected container's own compose labels
    # say which env it was started under (see do_fix_network), so this
    # doesn't need one passed in either.
    # Not env-scoped either: it packs the whole repo + service_data.
    if argv and argv[0] == "archive":
        if len(argv) < 2:
            error("usage: homeserver.py archive <destination-folder>")
            return 1
        return do_archive(argv[1])

    if argv and argv[0] == "fix-network":
        return do_fix_network(assume_yes="--yes" in argv or "-y" in argv)

    if len(argv) < 3:
        show_help()
        return 1

    env = argv[0]
    action = argv[1]
    rest = argv[2:]

    if env in ("help", "--help", "-h"):
        show_help()
        return 0
    if env not in ("dev", "prod"):
        error(f"Unknown env '{env}' — use dev or prod")
        show_help()
        return 1

    if action not in (
        "up", "-u", "down", "-d", "restart", "-r", "logs", "update",
        "backup", "restore", "snapshots", "dump", "migrate", "precreate", "reset",
    ):
        error(
            "Unknown action "
            f"'{action}' — use up, down, restart, logs, update, backup, restore, snapshots, dump, migrate, precreate, or reset"
        )
        show_help()
        return 1

    services_to_run: list[str] = []
    profile: str | None = None
    no_backup = False
    no_ml = False
    fresh = False
    update_flag = False
    assume_yes = False
    used_group_or_bundle = False
    snapshot: str | None = None
    image_flag: str | None = None
    run_all = run_core = run_daily = run_browser = run_office = run_automation_ai = run_extra = run_min = run_running = False

    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok == "--profile":
            i += 1
            if i >= len(rest):
                error("--profile requires a name (e.g. --profile runner)")
                return 1
            profile = rest[i]
        elif tok == "--no-backup":
            no_backup = True
        elif tok == "--no-ml":
            no_ml = True
        elif tok == "--no-wg":
            NO_WG_START = True
        elif tok == "--fresh":
            fresh = True
        elif tok == "--update":
            update_flag = True
        elif tok in ("--yes", "-y"):
            assume_yes = True
        elif tok == "--snapshot":
            i += 1
            if i >= len(rest):
                error("--snapshot requires a timestamp (e.g. --snapshot 20260710-160628)")
                return 1
            snapshot = rest[i]
        elif tok == "--image":
            i += 1
            if i >= len(rest):
                error("--image requires a tag or repo:tag (e.g. --image postgres:18.4-alpine)")
                return 1
            image_flag = rest[i]
        elif tok == "all":
            run_all = True
        elif tok == "core":
            run_core = True
        elif tok == "daily":
            run_daily = True
        elif tok == "browser":
            # Tier keyword — checked before the bare-bundle branch below, so
            # 'browser' means the whole browser tier (same members as the
            # Browser Hub bundle) with normal tier semantics.
            run_browser = True
        elif tok == "office":
            run_office = True
        elif tok == "automation-ai":
            run_automation_ai = True
        elif tok == "extra":
            run_extra = True
        elif tok == "min":
            run_min = True
        elif tok == "running":
            run_running = True
        elif tok.startswith("group:"):
            group_name = tok[len("group:"):]
            if group_name not in SERVICE_GROUPS:
                error(f"Unknown group '{group_name}' — valid groups: {', '.join(sorted(SERVICE_GROUPS))}")
                return 1
            services_to_run.extend(SERVICE_GROUPS[group_name])
            used_group_or_bundle = True
            # Only splice in a bundle's "requires" (e.g. nginx-plain for
            # 'browser') on actions that bring things up — never on
            # down/restart/update/backup/restore/dump, which must only ever
            # touch the bundle's own members. See BUNDLE_REQUIRES above.
            if group_name in BUNDLE_REQUIRES and action in ("up", "-u", "precreate"):
                services_to_run.extend(BUNDLE_REQUIRES[group_name])
        elif tok in BUNDLE_MEMBERS:
            # Bare bundle name (e.g. 'browser', not 'group:browser') — see
            # the BUNDLE_MEMBERS/BUNDLE_REQUIRES derivation above for why
            # this expands instead of targeting a single (nonexistent)
            # service directory.
            services_to_run.extend(BUNDLE_MEMBERS[tok])
            used_group_or_bundle = True
            if tok in BUNDLE_REQUIRES and action in ("up", "-u", "precreate"):
                services_to_run.extend(BUNDLE_REQUIRES[tok])
        else:
            if is_valid_service(tok):
                services_to_run.append(tok)
            else:
                error(f"Unknown service '{tok}'")
                show_help()
                return 1
        i += 1

    # A group can overlap with another group or an explicitly named service
    # (e.g. 'up group:notes group:productivity') — dedupe while preserving
    # first-seen order so nothing runs twice.
    services_to_run = list(dict.fromkeys(services_to_run))

    if not (run_all or run_core or run_daily or run_browser or run_office or run_automation_ai or run_extra or run_min or run_running) and not services_to_run:
        error("No services specified")
        show_help()
        return 1

    if no_ml:
        if action not in ("up", "-u") or services_to_run != ["immich"] or run_all or run_core or run_daily or run_browser or run_office or run_automation_ai or run_extra or run_min or run_running:
            error("--no-ml is only valid with 'up immich' on its own (excludes immich-ml)")
            return 1

    if fresh and action not in ("up", "-u"):
        error("--fresh is only valid with the up action")
        return 1

    if update_flag and action != "precreate":
        error("--update is only valid with the precreate action")
        return 1

    if action == "migrate" and (run_all or run_core or run_daily or run_browser or run_office or run_automation_ai or run_extra or run_min or run_running):
        error("migrate only works against explicitly named services, e.g. 'dev migrate forgejo' — no tier-wide migration")
        return 1

    if image_flag and action != "migrate":
        error("--image is only valid with the migrate action")
        return 1
    if image_flag and len(services_to_run) != 1:
        error("--image is only valid when migrating exactly one service")
        return 1

    if action in ("up", "-u"):
        ensure_network()
        exclude = ["immich-machine-learning"] if no_ml else None
        if run_all:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header(f"Starting all services (min + core + daily + browser + office + automation-ai + extra) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "All services", fresh=fresh)
        elif run_core:
            running = set(get_running_services())
            missing = [s for s in SERVICES_MIN if s not in running]
            if missing:
                header(f"Starting core services in {env} mode (bootstrapping missing min tier: {', '.join(missing)})...")
            else:
                header(f"Starting core services in {env} mode (min already running, left untouched)...")
            services = missing + SERVICES_CORE + services_to_run
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "Core services", fresh=fresh)
        elif run_daily:
            running = set(get_running_services())
            missing = [s for s in SERVICES_MIN + SERVICES_CORE if s not in running]
            if missing:
                header(f"Starting daily services in {env} mode (bootstrapping missing min/core: {', '.join(missing)})...")
            else:
                header(f"Starting daily services in {env} mode (min/core already running, left untouched)...")
            services = missing + SERVICES_DAILY + services_to_run
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "Daily services", fresh=fresh)
        elif run_browser:
            running = set(get_running_services())
            missing = [s for s in SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY if s not in running]
            if missing:
                header(f"Starting browser services in {env} mode (bootstrapping missing min/core/daily: {', '.join(missing)})...")
            else:
                header(f"Starting browser services in {env} mode (min/core/daily already running, left untouched)...")
            services = missing + SERVICES_BROWSER + services_to_run
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "Browser services", fresh=fresh)
        elif run_office:
            running = set(get_running_services())
            missing = [s for s in SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER if s not in running]
            if missing:
                header(f"Starting office services in {env} mode (bootstrapping missing min/core/daily/browser: {', '.join(missing)})...")
            else:
                header(f"Starting office services in {env} mode (min/core/daily/browser already running, left untouched)...")
            services = missing + SERVICES_OFFICE + services_to_run
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "Office services", fresh=fresh)
        elif run_automation_ai:
            running = set(get_running_services())
            missing = [s for s in SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE if s not in running]
            if missing:
                header(f"Starting automation-ai services in {env} mode (bootstrapping missing min/core/daily/browser/office: {', '.join(missing)})...")
            else:
                header(f"Starting automation-ai services in {env} mode (min/core/daily/browser/office already running, left untouched)...")
            services = missing + SERVICES_AUTOMATION_AI + services_to_run
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "Automation-AI services", fresh=fresh)
        elif run_extra:
            running = set(get_running_services())
            missing = [s for s in SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI if s not in running]
            if missing:
                header(f"Starting extra services in {env} mode (bootstrapping missing min/core/daily/browser/office/automation-ai: {', '.join(missing)})...")
            else:
                header(f"Starting extra services in {env} mode (min/core/daily/browser/office/automation-ai already running, left untouched)...")
            services = missing + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "Extra services", fresh=fresh)
        elif run_min:
            services = SERVICES_MIN + services_to_run
            header(f"Starting min services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_up, services, env, profile, "Min services", fresh=fresh)
        else:
            header(f"Starting services in {env} mode...")
            if used_group_or_bundle and not confirm_expansion(services_to_run, assume_yes):
                return 1
            run_list(do_up, services_to_run, env, profile, "Services", exclude=exclude, fresh=fresh)

    elif action == "precreate":
        ensure_network()
        if run_all:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header(f"Pre-creating all services (min + core + daily + browser + office + automation-ai + extra) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "All services", update=update_flag)
        elif run_core:
            services = SERVICES_MIN + SERVICES_CORE + services_to_run
            header(f"Pre-creating core services (min + core) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "Core services", update=update_flag)
        elif run_daily:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + services_to_run
            header(f"Pre-creating daily services (min + core + daily) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "Daily services", update=update_flag)
        elif run_browser:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + services_to_run
            header(f"Pre-creating browser services (min + core + daily + browser) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "Browser services", update=update_flag)
        elif run_office:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + services_to_run
            header(f"Pre-creating office services (min + core + daily + browser + office) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "Office services", update=update_flag)
        elif run_automation_ai:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + services_to_run
            header(f"Pre-creating automation-ai services (min + core + daily + browser + office + automation-ai) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "Automation-AI services", update=update_flag)
        elif run_extra:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header(f"Pre-creating extra services (min + core + daily + browser + office + automation-ai + extra) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "Extra services", update=update_flag)
        elif run_min:
            services = SERVICES_MIN + services_to_run
            header(f"Pre-creating min services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_precreate, services, env, profile, "Min services", update=update_flag)
        else:
            header(f"Pre-creating services in {env} mode...")
            if used_group_or_bundle and not confirm_expansion(services_to_run, assume_yes):
                return 1
            run_list(do_precreate, services_to_run, env, profile, "Services", update=update_flag)

    elif action in ("down", "-d"):
        if run_all:
            header("Stopping all services and profile containers (reverse order)...")
            # MANUAL services are never auto-started, but 'down all' is the
            # one command that stops everything, so include the ones actually
            # running (not stopped ones, which would only churn snapshots).
            running_manual = [s for s in SERVICES_MANUAL if s in get_running_services()]
            lst = list(reversed(SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + running_manual + services_to_run))
        elif run_core:
            header("Stopping core services (reverse order) — min stays running...")
            lst = list(reversed(SERVICES_CORE + services_to_run))
        elif run_daily:
            header("Stopping daily services (reverse order) — min/core stay running...")
            lst = list(reversed(SERVICES_DAILY + services_to_run))
        elif run_browser:
            header("Stopping browser services (reverse order) — min/core/daily stay running...")
            lst = list(reversed(SERVICES_BROWSER + services_to_run))
        elif run_office:
            header("Stopping office services (reverse order) — min/core/daily/browser stay running...")
            lst = list(reversed(SERVICES_OFFICE + services_to_run))
        elif run_automation_ai:
            header("Stopping automation-ai services (reverse order) — min/core/daily/browser/office stay running...")
            lst = list(reversed(SERVICES_AUTOMATION_AI + services_to_run))
        elif run_extra:
            header("Stopping extra services (reverse order) — min/core/daily/browser/office/automation-ai stay running...")
            lst = list(reversed(SERVICES_EXTRA + services_to_run))
        elif run_min:
            header("Stopping min services (reverse order)...")
            lst = list(reversed(SERVICES_MIN + services_to_run))
        else:
            header("Stopping services...")
            lst = services_to_run
        if (run_all or run_core or run_daily or run_browser or run_office or run_automation_ai or run_extra or run_min or used_group_or_bundle) and not confirm_expansion(lst, assume_yes):
            return 1
        # A Compose profile is opt-in by default, so a plain `compose down`
        # misses profile-only containers that were previously started (for
        # example GitLab's CI runner). Always select every profile for any
        # down target: stopping a service must release all of its resources,
        # whether it was selected by name, group, tier, or `all`.
        down_profile = "*"
        for service in lst:
            do_down(service, env, down_profile, no_backup=no_backup)
        # Reference count: stop a shared database server once no running
        # service uses it any more (see the Shared databases section).
        release_shared_dbs(env)
        print()
        success("Done")

    elif action in ("restart", "-r"):
        ensure_network()
        if run_all:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header(f"Restarting all services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "All services")
        elif run_core:
            services = SERVICES_MIN + SERVICES_CORE + services_to_run
            header(f"Restarting core services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "Core services")
        elif run_daily:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + services_to_run
            header(f"Restarting daily services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "Daily services")
        elif run_browser:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + services_to_run
            header(f"Restarting browser services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "Browser services")
        elif run_office:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + services_to_run
            header(f"Restarting office services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "Office services")
        elif run_automation_ai:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + services_to_run
            header(f"Restarting automation-ai services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "Automation-AI services")
        elif run_extra:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header(f"Restarting extra services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "Extra services")
        elif run_min:
            services = SERVICES_MIN + services_to_run
            header(f"Restarting min services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restart, services, env, profile, "Min services")
        else:
            header(f"Restarting services in {env} mode...")
            if used_group_or_bundle and not confirm_expansion(services_to_run, assume_yes):
                return 1
            run_list(do_restart, services_to_run, env, profile, "Services")

    elif action == "logs":
        service = services_to_run[0] if services_to_run else (SERVICES_MIN[0] if run_all else None)
        if service:
            do_logs(service, env)

    elif action == "update":
        ensure_network()
        if run_all:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header(f"Updating all services (min + core + daily + browser + office + automation-ai + extra) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "All services")
        elif run_core:
            services = SERVICES_MIN + SERVICES_CORE + services_to_run
            header(f"Updating core services (min + core) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "Core services")
        elif run_daily:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + services_to_run
            header(f"Updating daily services (min + core + daily) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "Daily services")
        elif run_browser:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + services_to_run
            header(f"Updating browser services (min + core + daily + browser) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "Browser services")
        elif run_office:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + services_to_run
            header(f"Updating office services (min + core + daily + browser + office) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "Office services")
        elif run_automation_ai:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + services_to_run
            header(f"Updating automation-ai services (min + core + daily + browser + office + automation-ai) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "Automation-AI services")
        elif run_extra:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header(f"Updating extra services (min + core + daily + browser + office + automation-ai + extra) in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "Extra services")
        elif run_min:
            services = SERVICES_MIN + services_to_run
            header(f"Updating min services in {env} mode...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_update, services, env, profile, "Min services")
        elif run_running:
            header(f"Updating running services in {env} mode...")
            lst = get_running_services()
            if not lst:
                warn("No running services detected")
                return 0
            info(f"Detected running services: {' '.join(lst)}")
            print()
            if not confirm_expansion(lst, assume_yes):
                return 1
            run_list(do_update, lst, env, profile, "Running services")
        else:
            header(f"Updating services in {env} mode...")
            if used_group_or_bundle and not confirm_expansion(services_to_run, assume_yes):
                return 1
            run_list(do_update, services_to_run, env, profile, "Services")

    elif action == "backup":
        if run_all:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header("Backing up all services (named volumes + service_data) to service_data/backup/...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "All services")
        elif run_core:
            services = SERVICES_MIN + SERVICES_CORE + services_to_run
            header("Backing up core services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "Core services")
        elif run_daily:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + services_to_run
            header("Backing up daily services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "Daily services")
        elif run_browser:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + services_to_run
            header("Backing up browser services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "Browser services")
        elif run_office:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + services_to_run
            header("Backing up office services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "Office services")
        elif run_automation_ai:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + services_to_run
            header("Backing up automation-ai services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "Automation-AI services")
        elif run_extra:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header("Backing up extra services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "Extra services")
        elif run_min:
            services = SERVICES_MIN + services_to_run
            header("Backing up min services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_backup, services, env, profile, "Min services")
        elif run_running:
            header("Backing up running services...")
            lst = get_running_services() + services_to_run
            if not lst:
                error("backup running: no running services detected, nothing to back up")
                return 1
            info(f"Detected running services: {' '.join(lst)}")
            if not confirm_expansion(lst, assume_yes):
                return 1
            run_list(do_backup, lst, env, profile, "Running services")
        else:
            header("Backing up services...")
            if not services_to_run:
                # `backup running` once matched nothing here and reported success: a backup that did
                # nothing must never look like one that worked.
                error("backup: no service named and no tier or target given, nothing to back up")
                return 1
            if used_group_or_bundle and not confirm_expansion(services_to_run, assume_yes):
                return 1
            run_list(do_backup, services_to_run, env, profile, "Services")
        # Backing up a stopped app starts its shared server to dump its
        # database; stop it again if nothing running needs it.
        release_shared_dbs(env)

    elif action == "restore":
        ensure_network()
        if snapshot and (run_all or run_core or run_daily or run_browser or run_office or run_automation_ai or run_extra or run_min):
            error("--snapshot only works when restoring a single named service")
            return 1
        if run_all:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header("Restoring all services from service_data/backup/...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "All services")
        elif run_core:
            services = SERVICES_MIN + SERVICES_CORE + services_to_run
            header("Restoring core services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "Core services")
        elif run_daily:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + services_to_run
            header("Restoring daily services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "Daily services")
        elif run_browser:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + services_to_run
            header("Restoring browser services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "Browser services")
        elif run_office:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + services_to_run
            header("Restoring office services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "Office services")
        elif run_automation_ai:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + services_to_run
            header("Restoring automation-ai services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "Automation-AI services")
        elif run_extra:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header("Restoring extra services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "Extra services")
        elif run_min:
            services = SERVICES_MIN + services_to_run
            header("Restoring min services...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_restore, services, env, profile, "Min services")
        else:
            header("Restoring services...")
            if used_group_or_bundle and not confirm_expansion(services_to_run, assume_yes):
                return 1
            run_list(do_restore, services_to_run, env, profile, "Services", snapshot=snapshot)
        release_shared_dbs(env)

    elif action == "reset":
        # Same target semantics as 'down': a tier keyword means just that
        # tier (never cascades into lower tiers). Order is startup order,
        # since each service comes back up as part of its own reset.
        if run_running:
            error("reset takes services, tiers or groups — not 'running'")
            return 1
        if run_all:
            lst = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + [s for s in SERVICES_MANUAL if s in get_running_services()] + services_to_run
        elif run_core:
            lst = SERVICES_CORE + services_to_run
        elif run_daily:
            lst = SERVICES_DAILY + services_to_run
        elif run_browser:
            lst = SERVICES_BROWSER + services_to_run
        elif run_office:
            lst = SERVICES_OFFICE + services_to_run
        elif run_automation_ai:
            lst = SERVICES_AUTOMATION_AI + services_to_run
        elif run_extra:
            lst = SERVICES_EXTRA + services_to_run
        elif run_min:
            lst = SERVICES_MIN + services_to_run
        else:
            lst = services_to_run
        header(f"Reset = snapshot, wipe, start blank ('restore <service>' undoes it): {' '.join(lst)}")
        # Never auto-confirmed: unlike other tier commands, a non-interactive
        # reset without -y refuses instead of proceeding (see the
        # homeserver-py-no-dry-run note in docs/08-maintenance.md).
        if not assume_yes:
            if not sys.stdin.isatty():
                error("reset deletes data — pass -y to confirm when not running interactively")
                return 1
            if input(f"Type 'reset' to snapshot and wipe {len(lst)} service(s): ").strip() != "reset":
                warn("Aborted — nothing changed")
                return 1
        ensure_network()
        run_list(do_reset, lst, env, profile, "Reset")
        release_shared_dbs(env)

    elif action == "snapshots":
        if not services_to_run:
            error(f"Specify a service: python homeserver.py {env} snapshots <service>")
            return 1
        for service in services_to_run:
            do_snapshots(service)

    elif action == "dump":
        if run_all:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header("Dumping all running services' databases to service_data/db_dump/...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "All services")
        elif run_core:
            services = SERVICES_MIN + SERVICES_CORE + services_to_run
            header("Dumping core services' databases...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "Core services")
        elif run_daily:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + services_to_run
            header("Dumping daily services' databases...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "Daily services")
        elif run_browser:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + services_to_run
            header("Dumping browser services' databases...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "Browser services")
        elif run_office:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + services_to_run
            header("Dumping office services' databases...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "Office services")
        elif run_automation_ai:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + services_to_run
            header("Dumping automation-ai services' databases...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "Automation-AI services")
        elif run_extra:
            services = SERVICES_MIN + SERVICES_CORE + SERVICES_DAILY + SERVICES_BROWSER + SERVICES_OFFICE + SERVICES_AUTOMATION_AI + SERVICES_EXTRA + services_to_run
            header("Dumping extra services' databases...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "Extra services")
        elif run_min:
            services = SERVICES_MIN + services_to_run
            header("Dumping min services' databases...")
            if not confirm_expansion(services, assume_yes):
                return 1
            run_list(do_dump, services, env, profile, "Min services")
        else:
            header("Dumping databases...")
            if used_group_or_bundle and not confirm_expansion(services_to_run, assume_yes):
                return 1
            run_list(do_dump, services_to_run, env, profile, "Services")

    elif action == "migrate":
        ensure_network()
        header(f"Migrating database{' to ' + image_flag if image_flag else ' to postgres-alpine'}...")
        run_list(do_migrate, services_to_run, env, profile, "Services", image_override=image_flag)

    return 0


if __name__ == "__main__":
    sys.exit(main())
