#!/usr/bin/env python3
"""kubernetes/k8s.py — start/stop services in the Kubernetes pilot, mirroring
homeserver.py's tier/group/service UX for the (separate, parallel) Compose
stack.

Usage:
  uv run kubernetes/k8s.py up   <min|core|daily|office|automation-ai|extra|manual|all|group:<name>|service...> [--yes] [--dry-run]
  uv run kubernetes/k8s.py down <min|core|daily|office|automation-ai|extra|manual|all|group:<name>|service...> [--yes] [--dry-run]
  uv run kubernetes/k8s.py status [min|core|daily|...|group:<name>|service...]

  A tier keyword, 'all', or 'group:<name>' prints the resolved service list
  and asks for confirmation before acting (skip with --yes/-y) — same
  asymmetry as homeserver.py's confirm_expansion(): naming explicit
  service(s) directly never prompts, you already said exactly what you want.

  --dry-run prints exactly what would happen (resolved services, matched
  Kubernetes resources, the kubectl/ArgoCD commands) without executing any
  mutating command. Also how this tool is verified before a live cluster
  exists — see kubernetes/README.md's "Current status".

Tiers and groups are read live from ../services.json (the same file
homeserver.py reads — one source of truth, not a second hand-maintained
list) and intersected with what's actually present under kubernetes/apps/,
since only 64 of 70 Compose services are ported here so far. Anything in a
tier/group that isn't ported yet is silently skipped, not an error — same
"partial tier is fine" idiom homeserver.py's own 'up core' already uses.

Why this exists instead of hand-typed kubectl: every ArgoCD Application in
this pilot has automated sync with selfHeal:true (see kubernetes/README.md),
so a plain `kubectl scale --replicas=0` gets silently reverted within one
sync cycle — ArgoCD notices the drift from git (which still says replicas:1)
and scales back up. kubernetes/TROUBLESHOOTING.md documents the correct
manual sequence (disable automated sync first, then scale, then suspend any
CronJobs); this tool just automates that sequence per-service instead of
requiring three hand-typed commands each time.

PVCs and Secrets are never touched by up/down — scaling to 0 only stops
pods, all data (Postgres volumes, uploaded files, config) stays exactly as
it was for whenever a service is scaled back up. This pilot has no
backup/snapshot mechanism of its own yet (unlike Compose's automatic
snapshot-on-down) — that's a separate, not-yet-built piece of pilot infra,
not something this tool invents a substitute for.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# ── Paths & config ──────────────────────────────────────────────────

K8S_DIR = Path(__file__).resolve().parent
BASE_DIR = K8S_DIR.parent
APPS_DIR = K8S_DIR / "apps"
SERVICES_JSON_PATH = BASE_DIR / "services.json"

NAMESPACE = "apps"
ARGOCD_NAMESPACE = "argocd"

# kind names the cluster "kind-cluster" (explicit `name:` field in
# kubernetes/kind-config.yaml — kind's own unnamed default is literally
# "kind", easy to collide with some other unrelated kind cluster on the
# same machine), giving context "kind-<cluster-name>" = "kind-kind-cluster"
# per kind's own naming convention. A mismatch here doesn't block anything
# (someone may legitimately rename the cluster later), it just warns
# loudly before a mutating command runs against a kubeconfig context that
# might not be this pilot's cluster at all.
EXPECTED_CONTEXT = "kind-kind-cluster"

TIER_NAMES = ["min", "core", "daily", "office", "automation-ai", "extra", "manual"]

# Kinds this tool will actually scale/suspend. Everything else under
# kubernetes/apps/ (Job, Service, ConfigMap, Secret, PersistentVolumeClaim,
# HTTPRoute, Middleware, ServiceAccount, ClusterRoleBinding) is left alone —
# Job in particular must never be scaled, it's a run-to-completion resource
# (db-init-job.yaml, schema-setup-job.yaml, etc.), not a long-running workload.
WORKLOAD_KINDS = ["deployment", "statefulset", "cronjob"]

# Resources that exist under a service's directory but don't follow the
# "<dir>" or "<dir>-<suffix>" naming convention every other service uses —
# found by an exhaustive audit of every Deployment/StatefulSet/CronJob name
# in kubernetes/apps/*/*.yaml against its containing directory. Every other
# service (57 of 65 checked) needs no entry here at all.
RESOURCE_EXCEPTIONS: dict[str, list[str]] = {
    "guacamole": ["guacd"],
    "observability": ["alloy", "cadvisor", "grafana", "loki", "node-exporter", "prometheus"],
}


# ── services.json — same source of truth homeserver.py reads ───────


def load_services_json(path: Path) -> dict:
    if not path.is_file():
        print(f"{path} not found — this repo can't run without it (tiers/groups are defined there).", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


_SERVICES_DATA = load_services_json(SERVICES_JSON_PATH)


def is_k8s_ported(entry: dict) -> bool:
    """Mirrors homeserver.py's is_managed_service(), but checked against
    kubernetes/apps/<slug>/ instead of services/<slug>/ — only entries with
    an independent tier, not virtual (landing-page-only bundle cards), and
    actually ported to this pilot count as a startable k8s service."""
    return bool(entry.get("tier")) and not entry.get("virtual") and (APPS_DIR / entry["slug"]).is_dir()


K8S_TIERS: dict[str, list[str]] = {
    tier: [s["slug"] for s in _SERVICES_DATA["services"] if s.get("tier") == tier and is_k8s_ported(s)]
    for tier in TIER_NAMES
}

# category/subcategory -> ordered list of slugs, same construction as
# homeserver.py's SERVICE_GROUPS, filtered to k8s-ported services only.
K8S_GROUPS: dict[str, list[str]] = {}
CATEGORY_SUBGROUPS: dict[str, set[str]] = {}
for _s in _SERVICES_DATA["services"]:
    if not is_k8s_ported(_s):
        continue
    for _key in ("category", "subcategory"):
        _val = _s.get(_key)
        if _val:
            K8S_GROUPS.setdefault(_val, []).append(_s["slug"])
    _cat, _sub = _s.get("category"), _s.get("subcategory")
    if _cat and _sub:
        CATEGORY_SUBGROUPS.setdefault(_cat, set()).add(_sub)
del _s, _key, _val, _cat, _sub

# "all" = every tier except manual — same as homeserver.py's 'up all'
# (manual-only services are excluded there too; start them by name).
ALL_PORTED = [svc for tier in TIER_NAMES if tier != "manual" for svc in K8S_TIERS[tier]]

# min/core are the only tiers committed to git at replicas:1 — they
# self-heal UP (survive a reboot / full ArgoCD resync automatically, same
# as core infra always has). Every other tier is committed at replicas:0
# and self-heals DOWN — opt-in, stays off unless deliberately started,
# same idiom as homeserver.py's daily/office/automation-ai/extra/manual
# tiers never auto-starting. This means up/down manage ArgoCD sync in
# OPPOSITE directions depending on which side of this line a service is
# on — see sync_direction() below for why.
BASELINE_ON = set(K8S_TIERS["min"]) | set(K8S_TIERS["core"])


def is_baseline_on(service: str) -> bool:
    return service in BASELINE_ON

# Every kubernetes/apps/<dir> — including non-services.json infra like
# 'dashboard' and 'authentik's own forward-auth-middleware.yaml' — used as
# the universe for resource-name disambiguation (see resolve_resources()),
# not for tier/group membership.
ALL_SERVICE_DIRS = sorted(p.name for p in APPS_DIR.iterdir() if p.is_dir())


# ── Colored output (same helpers/glyphs as homeserver.py) ──────────

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


# ── kubectl helpers ──────────────────────────────────────────────────
#
# Deliberately no DockerBackend-style ABC here (unlike homeserver.py's
# genuine dual-implementation need for Docker vs. Podman sockets) — there's
# exactly one backend for this tool, kubectl, so a couple of plain
# functions are enough; a backend-swap abstraction would be structure this
# problem doesn't need.


def kubectl_run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["kubectl", *args], capture_output=True, text=True, check=check)


def kubectl_json(args: list[str]) -> dict | None:
    """Returns None (not a raised exception) on any failure — including
    kubectl not being installed or no cluster being reachable — so status
    can degrade gracefully to 'no live cluster reachable' instead of a raw
    traceback. There is no live cluster yet as of this pilot's current
    status (see kubernetes/README.md), so this path is the normal case
    today, not an edge case."""
    try:
        result = kubectl_run([*args, "-o", "json"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def current_context() -> str | None:
    try:
        result = kubectl_run(["config", "current-context"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip()


def check_context(dry_run: bool) -> bool:
    """Verify kubectl is pointed at this pilot's cluster before any mutating
    command runs — a kubeconfig with multiple contexts touching the wrong
    cluster is a much worse failure mode than a slightly annoying prompt.
    Not enforced during --dry-run (nothing mutates, and this also doubles
    as this tool's own no-live-cluster verification path)."""
    ctx = current_context()
    if ctx is None:
        if dry_run:
            warn("kubectl not reachable (no live cluster yet?) — continuing, --dry-run doesn't need one")
            return True
        error("kubectl not reachable — is a cluster running? (kind create cluster --config kubernetes/kind-config.yaml)")
        return False
    if ctx != EXPECTED_CONTEXT:
        warn(f"current kubectl context is '{ctx}', expected '{EXPECTED_CONTEXT}' — double-check this is the right cluster")
        if not dry_run:
            try:
                reply = input(f"\n{BOLD}Continue against '{ctx}' anyway? [y/N]{RESET} ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print()
                return False
            if reply not in ("y", "yes"):
                info("Cancelled")
                return False
    return True


# ── Target resolution (tier / group:<name> / service / all) ────────


def resolve_targets(tokens: list[str]) -> tuple[list[str], bool]:
    """Resolves CLI target tokens into an ordered, deduped list of k8s-ported
    service slugs. Returns (services, was_expansion) — was_expansion is True
    if any token was a tier/group/'all' keyword (triggers confirm_expansion),
    False if every token was a literal service name (never prompts) — same
    asymmetry as homeserver.py's main()."""
    resolved: list[str] = []
    was_expansion = False

    def add_all(slugs: list[str]) -> None:
        for slug in slugs:
            if slug not in resolved:
                resolved.append(slug)

    for token in tokens:
        if token == "all":
            add_all(ALL_PORTED)
            was_expansion = True
        elif token in TIER_NAMES:
            add_all(K8S_TIERS[token])
            was_expansion = True
        elif token.startswith("group:"):
            group_name = token[len("group:"):]
            if group_name not in K8S_GROUPS:
                error(f"Unknown group '{group_name}' — valid groups: {', '.join(sorted(K8S_GROUPS))}")
                sys.exit(1)
            add_all(K8S_GROUPS[group_name])
            was_expansion = True
        else:
            if not (APPS_DIR / token).is_dir():
                error(f"Unknown service '{token}' — no kubernetes/apps/{token}/ directory")
                sys.exit(1)
            add_all([token])

    return resolved, was_expansion


def confirm_expansion(services: list[str], assume_yes: bool) -> bool:
    """Same idiom as homeserver.py's confirm_expansion(): skipped for a
    literal service list, skipped with --yes or a non-TTY stdin (scripted
    use must never hang on an unanswerable prompt)."""
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


# ── Resource discovery (name-prefix matching, no new labels needed) ─


def get_all_workload_names() -> dict[str, list[str]]:
    """{'deployment': [...], 'statefulset': [...], 'cronjob': [...]} of every
    resource of each kind currently in the apps namespace. Empty lists (not
    an error) if the cluster isn't reachable — callers already know from
    check_context() whether that's expected."""
    result: dict[str, list[str]] = {kind: [] for kind in WORKLOAD_KINDS}
    names = kubectl_json(["get", *WORKLOAD_KINDS, "-n", NAMESPACE])
    if names is None or "items" not in names:
        return result
    for item in names["items"]:
        kind = item.get("kind", "").lower()
        name = item.get("metadata", {}).get("name")
        if kind in result and name:
            result[kind].append(name)
    return result


def _matches_service(name: str, service: str) -> bool:
    return name == service or name.startswith(service + "-")


def resolve_resources(service: str, all_names: dict[str, list[str]]) -> dict[str, list[str]]:
    """Which Deployment/StatefulSet/CronJob resources belong to `service`.
    Prefix match against the service's own directory name, plus:
      - longest-match-wins disambiguation against every OTHER known service
        directory (generic — this is what correctly excludes
        stirling-pdf-lite's resources when the target is stirling-pdf, and
        will auto-handle any future analogous case without a hardcoded
        exception for that specific pair)
      - RESOURCE_EXCEPTIONS for the two audited non-conforming directories
        (guacamole's guacd, observability's 6 unprefixed Deployments)
    """
    extra_names = RESOURCE_EXCEPTIONS.get(service, [])
    matched: dict[str, list[str]] = {}
    for kind, names in all_names.items():
        kept = []
        for name in names:
            if name in extra_names:
                kept.append(name)
                continue
            if not _matches_service(name, service):
                continue
            # Exclude if a longer, different known service directory also
            # claims this exact resource name more specifically.
            more_specific = any(
                other != service and len(other) > len(service) and _matches_service(name, other)
                for other in ALL_SERVICE_DIRS
            )
            if not more_specific:
                kept.append(name)
        if kept:
            matched[kind] = kept
    return matched


# ── up / down / status ──────────────────────────────────────────────


def argocd_patch(service: str, sync_enabled: bool, dry_run: bool) -> None:
    patch = (
        '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
        if sync_enabled
        else '{"spec":{"syncPolicy":{"automated":null}}}'
    )
    args = ["-n", ARGOCD_NAMESPACE, "patch", "application", service, "--type", "merge", "-p", patch]
    if dry_run:
        print(f"    [dry-run] kubectl {' '.join(args)}")
        return
    try:
        kubectl_run(args, check=True)
    except subprocess.CalledProcessError as e:
        warn(f"    could not patch ArgoCD Application '{service}' (not applied to a live cluster yet?): {e.stderr.strip() if e.stderr else e}")


def scale(kind: str, name: str, replicas: int, dry_run: bool) -> bool:
    args = ["scale", f"{kind}/{name}", "-n", NAMESPACE, f"--replicas={replicas}"]
    if dry_run:
        print(f"    [dry-run] kubectl {' '.join(args)}")
        return True
    try:
        kubectl_run(args, check=True)
        return True
    except subprocess.CalledProcessError as e:
        error(f"    failed to scale {kind}/{name}: {e.stderr.strip() if e.stderr else e}")
        return False


def suspend_cronjob(name: str, suspend: bool, dry_run: bool) -> bool:
    patch = '{"spec":{"suspend":true}}' if suspend else '{"spec":{"suspend":false}}'
    args = ["patch", "cronjob", name, "-n", NAMESPACE, "-p", patch]
    if dry_run:
        print(f"    [dry-run] kubectl {' '.join(args)}")
        return True
    try:
        kubectl_run(args, check=True)
        return True
    except subprocess.CalledProcessError as e:
        error(f"    failed to {'suspend' if suspend else 'resume'} cronjob/{name}: {e.stderr.strip() if e.stderr else e}")
        return False


def sync_direction(service: str, action: str) -> tuple[bool, int]:
    """(sync_enabled, target_replicas) for `service` + `action` ('up' or
    'down') — the one piece of logic that has to know which way each tier
    self-heals, kept as a small pure function so it's unit-testable without
    a live cluster.

    min/core (BASELINE_ON) are committed to git at replicas:1 and meant to
    self-heal UP — 'up' enables sync (ArgoCD brings/keeps it at git's 1),
    'down' disables sync first (temporary override, or selfHeal reverts
    the scale-down within one sync cycle — see kubernetes/TROUBLESHOOTING.md's
    "pausing a service" note).

    Everything else is committed to git at replicas:0 and self-heals DOWN
    — the two directions are the exact mirror image: 'up' has to DISABLE
    sync first (git says 0; leaving sync on would let selfHeal revert the
    manual scale-up within one cycle, same race as the min/core 'down'
    case just flipped), 'down' enables sync so it settles back to git's
    committed 0 instead of needing yet another manual step later.

    In both action branches, argocd_patch() is called before scale() in
    do_up/do_down below — that ordering matters for whichever branch is
    disabling sync (must happen first to close the race window), and is
    harmless for whichever branch is enabling it (nothing to race against,
    both push toward the same target)."""
    baseline_on = is_baseline_on(service)
    if action == "up":
        return (baseline_on, 1)
    return (not baseline_on, 0)


def do_up(services: list[str], dry_run: bool) -> int:
    all_names = get_all_workload_names()
    failures: list[str] = []
    for service in services:
        info(f"up: {service}")
        sync_enabled, target = sync_direction(service, "up")
        resources = resolve_resources(service, all_names)
        if not resources:
            warn(f"  no matching Deployment/StatefulSet/CronJob found for '{service}' (already scaled down, or not applied to a live cluster yet)")
        argocd_patch(service, sync_enabled=sync_enabled, dry_run=dry_run)
        ok = True
        for name in resources.get("cronjob", []):
            ok = suspend_cronjob(name, suspend=False, dry_run=dry_run) and ok
        for kind in ("deployment", "statefulset"):
            for name in resources.get(kind, []):
                ok = scale(kind, name, replicas=target, dry_run=dry_run) and ok
        if ok:
            # Baseline-off services staying up outside their tier default
            # is a durable override, not a fluke — spec.replicas and the
            # Application's disabled syncPolicy are both persisted
            # control-plane state (etcd), so this survives a reboot same
            # as anything else. Only an explicit 'down' on this service
            # (or manually re-enabling its sync) clears it.
            tag = "" if sync_enabled else " (override — stays up until you run 'down' on it, survives a reboot)"
            success(f"  {service} up{tag}")
        else:
            failures.append(service)
    return _summarize(failures)


def do_down(services: list[str], dry_run: bool) -> int:
    all_names = get_all_workload_names()
    failures: list[str] = []
    for service in services:
        info(f"down: {service}")
        sync_enabled, target = sync_direction(service, "down")
        resources = resolve_resources(service, all_names)
        if not resources:
            warn(f"  no matching Deployment/StatefulSet/CronJob found for '{service}' (already scaled down, or not applied to a live cluster yet)")
        argocd_patch(service, sync_enabled=sync_enabled, dry_run=dry_run)
        ok = True
        for name in resources.get("cronjob", []):
            ok = suspend_cronjob(name, suspend=True, dry_run=dry_run) and ok
        for kind in ("deployment", "statefulset"):
            for name in resources.get(kind, []):
                ok = scale(kind, name, replicas=target, dry_run=dry_run) and ok
        if ok:
            success(f"  {service} down (PVCs/Secrets untouched)")
        else:
            failures.append(service)
    return _summarize(failures)


def _summarize(failures: list[str]) -> int:
    print(f"\n{BOLD}{'━' * 40}{RESET}")
    if failures:
        error(f"{len(failures)} service(s) had failures: {', '.join(failures)}")
        print(f"{BOLD}{'━' * 40}{RESET}\n")
        return 1
    print(f"{BOLD}{'━' * 40}{RESET}\n")
    return 0


def do_status(target_services: list[str] | None) -> int:
    ctx = current_context()
    if ctx is None:
        warn("no live cluster reachable — showing tier/group membership only, no running-state data")
    all_names = get_all_workload_names() if ctx else {kind: [] for kind in WORKLOAD_KINDS}

    def is_up(service: str) -> bool:
        resources = resolve_resources(service, all_names)
        # "up" = at least one matched Deployment/StatefulSet actually has a
        # live resource — CronJob suspend state isn't part of this glyph,
        # same as homeserver.py's own running-container check.
        return bool(resources.get("deployment") or resources.get("statefulset"))

    scope = set(target_services) if target_services else None

    def is_override(service: str) -> bool:
        # Live state disagreeing with what the service's tier baseline
        # would produce IS the definition of an override — a baseline-off
        # service that's up, or a baseline-on service that's down. No
        # extra ArgoCD Application fetch needed: this comparison alone
        # tells the whole story, since do_up/do_down are what put a
        # service in that state in the first place.
        return is_up(service) != is_baseline_on(service)

    def show_tier(label: str, services: list[str]) -> None:
        services = [s for s in services if scope is None or s in scope]
        if not services:
            return
        print(f"  {BOLD}{label}:{RESET}")
        for s in services:
            marker = f"{GREEN}●{RESET}" if is_up(s) else "○"
            tag = f" {YELLOW}(override){RESET}" if ctx and is_override(s) else ""
            print(f"    {marker} {s}{tag}")
        print()

    header("Service status (● up, ○ down):")
    for tier in TIER_NAMES:
        show_tier(tier.upper(), K8S_TIERS[tier])

    checked = [s for tier in TIER_NAMES for s in K8S_TIERS[tier] if scope is None or s in scope]
    up_count = sum(1 for s in checked if is_up(s))
    success(f"{up_count}/{len(checked)} service(s) up")

    if scope is None:
        print()
        print(f"  {BOLD}Groups ({len(K8S_GROUPS)} — 'up group:<name>' starts exactly these):{RESET}")
        categories = {s.get("category") for s in _SERVICES_DATA["services"] if is_k8s_ported(s) and s.get("category")}
        for cat in sorted(categories):
            members = K8S_GROUPS[cat]
            up = sum(1 for s in members if is_up(s))
            print(f"    {BOLD}{cat}{RESET} ({up}/{len(members)} up): {' '.join(members)}")
            for sub in sorted(CATEGORY_SUBGROUPS.get(cat, [])):
                sub_members = K8S_GROUPS[sub]
                sub_up = sum(1 for s in sub_members if is_up(s))
                print(f"      {BOLD}{sub}{RESET} ({sub_up}/{len(sub_members)} up): {' '.join(sub_members)}")

    return 0


# ── CLI ───────────────────────────────────────────────────────────────


def print_usage() -> None:
    print(__doc__)


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print_usage()
        return 0

    action = argv[0]
    if action not in ("up", "down", "status"):
        error(f"Unknown action '{action}' — expected 'up', 'down', or 'status'")
        print_usage()
        return 1

    rest = argv[1:]
    dry_run = "--dry-run" in rest
    assume_yes = "--yes" in rest or "-y" in rest
    tokens = [t for t in rest if t not in ("--dry-run", "--yes", "-y")]

    if action == "status":
        services, _ = resolve_targets(tokens) if tokens else ([], False)
        return do_status(services or None)

    if not tokens:
        error(f"'{action}' needs at least one target — a tier, group:<name>, 'all', or a service name")
        print_usage()
        return 1

    services, was_expansion = resolve_targets(tokens)
    if not services:
        warn("nothing to do — resolved target list is empty (tier/group has no k8s-ported services yet)")
        return 0

    if was_expansion and not confirm_expansion(services, assume_yes):
        return 1

    if not check_context(dry_run):
        return 1

    if action == "up":
        return do_up(services, dry_run)
    return do_down(services, dry_run)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
