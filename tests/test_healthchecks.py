"""Every long-running container needs a healthcheck: in compose, built into its
image, or — deliberately — none, with the reason recorded here. A new service
or container can't ship without one of the three (docs/10-new-services.md,
"How fixes are chosen"). Lists below were verified live on 2026-10-02."""

from __future__ import annotations


import yaml
from conftest import each

import homeserver as hs

# Containers whose image ships its own HEALTHCHECK (verified with
# `docker image inspect` / `skopeo inspect --config`). A compose
# `healthcheck:` would silently replace these, so don't add one.
IMAGE_HEALTHCHECK = {
    "atuin": "curl /healthz",
    "authentik-server": "ak healthcheck",
    "authentik-worker": "ak healthcheck",
    "bichon": "curl /api/status",
    "firefly": "curl $HEALTHCHECK_PATH (/healthcheck)",
    "firefly-importer": "curl $HEALTHCHECK_PATH",
    "guacd": "nc -z 127.0.0.1 4822 (timing-only override in compose)",
    "immich-server": "immich-healthcheck",
    "immich-ml": "python3 healthcheck.py",
    "immich-db": "/usr/local/bin/healthcheck.sh",
    "jellyfin": "curl $HEALTHCHECK_URL",
    "mailpit": "/mailpit readyz",
    "mattermost": "mmctl system status --local",
    "mealie": "$MEALIE_HOME/healthcheck.sh",
    "paperless": "curl http://localhost:8000",
    "plane-web": "curl http://127.0.0.1:3000/",
    "plane-admin": "curl http://127.0.0.1:3000/",
    "plane-space": "curl http://127.0.0.1:3000/spaces/",
    "uptime-kuma": "extra/healthcheck",
    "vaultwarden": "/healthcheck.sh (timing-only override in compose)",
    "wg-easy": "wg show | grep -q interface (timing-only override in compose)",
    "whiteboard": "node GET :3002",
}

# No healthcheck on purpose — each with the reason.
NO_HEALTHCHECK = {
    "adguard-watchdog": "is itself a monitor (curl loop restarting adguard-home)",
    "cloudflared-watchdog": "is itself a monitor",
    "appflowy-web": "upstream AppFlowy-Cloud compose defines none; static frontend behind appflowy-nginx",
    "appflowy-admin": "upstream AppFlowy-Cloud compose defines none; served under a sub-path behind appflowy-nginx",
    "erpnext-queue-short": "background worker, no listener or health command",
    "erpnext-queue-long": "background worker, no listener or health command",
    "erpnext-scheduler": "background worker, no listener or health command",
    "firefly-cron": "cron loop in plain alpine, nothing to probe",
    "nextcloud-cron": "cron loop, nothing to probe",
    "forgejo-runner": "CI runner, no health endpoint",
    "gitlab-runner": "CI runner, no health endpoint",
    "immich-offline-remover": "periodic job, no listener",
    "penpot-exporter": "upstream penpot compose defines none",
    "karakeep-chrome": "upstream karakeep compose defines none; the karakeep app reports browser reachability",
    "plane-worker": "celery worker, no listener",
    "plane-beat": "celery beat, no listener",
    "portainer": "image has no shell or HTTP client, so no probe can run",
    "temporal-admin-tools": "interactive toolbox container, not a server",
    "temporal-worker": "your workflow worker, no listener",
}


def containers():
    out = []
    for svc in sorted(p.name for p in hs.SERVICES_DIR.iterdir() if (p / hs.base_file(p.name)).is_file()):
        doc = yaml.safe_load((hs.SERVICES_DIR / svc / hs.base_file(svc)).read_text()) or {}
        for name, d in (doc.get("services") or {}).items():
            d = d or {}
            oneshot = str(d.get("restart", "")).strip('"') in ("no", "on-failure")
            out.append((svc, d.get("container_name", name), d, oneshot))
    return out


def test_long_running_container_has_a_healthcheck_story():
    each(containers(), _long_running_container_has_a_healthcheck_story, ids=lambda x: x if isinstance(x, str) else "")


def _long_running_container_has_a_healthcheck_story(svc, ctr, d, oneshot):
    if oneshot:
        return
    hc = d.get("healthcheck") or {}
    # A compose healthcheck without 'test' only retunes timing; the image's
    # own command still runs (Docker inherits an empty Test from the image).
    has_compose = bool(hc.get("test")) and not hc.get("disable")
    covered = has_compose or ctr in IMAGE_HEALTHCHECK or ctr in NO_HEALTHCHECK
    assert covered, (
        f"{svc}/{ctr} has no healthcheck: add one (upstream's first — see docs/10-new-services.md), "
        f"list its image's own HEALTHCHECK in IMAGE_HEALTHCHECK, or justify it in NO_HEALTHCHECK"
    )
    if has_compose:
        assert ctr not in IMAGE_HEALTHCHECK, f"{ctr}: compose healthcheck overrides the image's own ({IMAGE_HEALTHCHECK[ctr]})"
        assert ctr not in NO_HEALTHCHECK, f"{ctr} has a healthcheck now; drop it from NO_HEALTHCHECK"


def test_exception_lists_only_name_real_containers():
    names = {c for _, c, _, _ in containers()}
    stale = sorted((set(IMAGE_HEALTHCHECK) | set(NO_HEALTHCHECK)) - names)
    assert not stale, f"exception lists name containers that no longer exist: {stale}"



TCP_PG_ISREADY = sorted(set(hs.SERVICES_MIN + hs.SERVICES_CORE) | {"shared-postgres"})


def test_pg_isready_probes_tcp_not_the_socket():
    each(TCP_PG_ISREADY, _pg_isready_probes_tcp_not_the_socket)


def _pg_isready_probes_tcp_not_the_socket(svc):
    """On a fresh volume the postgres image's init runs a socket-only temporary
    server; a socket pg_isready reports ready then, and the app starts into
    'connection refused' when it's stopped. '-h 127.0.0.1' only answers once
    the real server listens (postgresql.org BUG #15222). Above CORE, apps
    copying upstream's compose verbatim keep upstream's form."""
    doc = yaml.safe_load((hs.SERVICES_DIR / svc / hs.base_file(svc)).read_text()) or {}
    for name, d in (doc.get("services") or {}).items():
        test = ((d or {}).get("healthcheck") or {}).get("test") or []
        cmd = " ".join(test) if isinstance(test, list) else str(test)
        if "pg_isready" in cmd:
            assert "-h " in cmd, f"{svc}/{name}: pg_isready must probe TCP (-h 127.0.0.1), got: {cmd}"
