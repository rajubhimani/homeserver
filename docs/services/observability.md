# Observability (Grafana + Prometheus + Loki)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Metrics and log dashboards covering every container in the stack — Prometheus for metrics, Loki for logs, Grafana as the single UI over both.
**Port:** `8134` (Grafana) / `8135` (Prometheus) (host) → `3000` / `9090` (container) | **Data:** `service_data/data/observability/{grafana,prometheus,loki}/` | **Requires:** nothing (all six containers are self-contained, no shared Postgres) | **Memory:** untuned, expect roughly Grafana ~150MB, Prometheus ~200MB+ (grows with retention/cardinality), Loki ~150MB, Alloy ~80MB, cAdvisor ~80MB, node-exporter ~20MB

---

## What it is

Six containers, one directory, no other service needs to change to be monitored:

- **`prometheus`** — scrapes metrics (from `cadvisor` and `node-exporter` only, today — see "What's actually monitored" below) and stores them
- **`loki`** — stores logs, single-binary/filesystem mode (no object storage backend needed at this scale)
- **`alloy`** — ships every container's stdout/stderr to Loki. Replaces Promtail, which went **EOL 2026-03-02** — Alloy is Grafana Labs' supported successor. Discovers containers via the Docker socket (`discovery.docker`), so nothing needs to be configured per-service — new containers are picked up automatically. FastAPI services in this stack already emit Loki-compatible JSON to stdout; that's queryable in Grafana with `| json` in LogQL, no special pipeline stage needed.
- **`cadvisor`** — per-container CPU/memory/network/disk metrics, scraped by Prometheus. Needs `privileged: true` and broad read-only host mounts (`/rootfs`, `/sys`, `/var/lib/docker`, the Docker socket) — standard requirement for cAdvisor, not specific to this stack.
- **`node-exporter`** — host-level CPU/memory/disk/network metrics, scraped by Prometheus. Runs on the `homeserver` bridge network (not `network_mode: host`, unlike most node-exporter recipes) to match this stack's one-network convention — trades away a few network-interface-level stats for consistency with every other service here.
- **`grafana`** — the dashboard UI. Prometheus and Loki datasources are auto-provisioned via `grafana/provisioning/datasources/datasources.yml`; no manual datasource setup needed after first boot.

## What's actually monitored

Prometheus only scrapes `cadvisor`, `node-exporter`, and itself out of the box. **None of the other ~50 services in this stack expose a `/metrics` endpoint today** — adding that is a per-service effort (an app-specific exporter, or the app's own built-in metrics endpoint if it has one) and was out of scope for standing up the stack itself. What you get immediately:

- Per-container CPU/memory/network/disk usage for every running container (via cadvisor) — this alone covers "is something eating all the RAM" without touching any other service.
- Host-level CPU/memory/disk/network (via node-exporter).
- Every container's logs, searchable and filterable in Grafana's Explore view (via Alloy → Loki) — including structured JSON fields from any service that logs JSON, queryable with LogQL's `| json`.

To add real application metrics for a specific service later: add a scrape target to `observability/prometheus/prometheus.yml` pointing at that service's `/metrics` route (or its exporter sidecar), then recreate the `prometheus` container.

## What's public vs. internal-only

Only **`grafana.${DOMAIN}`** gets a public nginx-plain route. Prometheus, Loki, Alloy, cAdvisor, and node-exporter have no authentication of their own — they're reachable only over the internal `homeserver` Docker network (Prometheus/Loki via Grafana's datasource proxy, cadvisor/node-exporter via Prometheus's scrape). Prometheus does get a **dev-only host port** (`8135`, loopback-only in prod) for verifying scrape targets directly at `http://localhost:8135/targets` — don't rely on that in prod without also putting auth in front of it if you ever need it exposed further.

## Setup

```bash
cp services/observability/.env.example services/observability/.env
# set GRAFANA_ADMIN_PASSWORD to something real — the example default is a placeholder
uv run homeserver.py dev up observability
```

Grafana admin login is `${GRAFANA_ADMIN_USER}` / `${GRAFANA_ADMIN_PASSWORD}` from `.env` (defaults to `admin`). No public signup — `GF_USERS_ALLOW_SIGN_UP` is hardcoded `false` in `compose.yml`, matching Grafana's own default; this is an admin-provisioned dashboard, not a service with real end users.

Three dashboards are pre-provisioned as code (same mechanism as the
datasources — no manual import needed, matches official Grafana
guidance of loading dashboards from files rather than clicking through
the UI): **Node Exporter Full** (grafana.com ID `1860`), **cadvisor
dashboard** (ID `19792`), and this repo's own **Stack Overview**
(`stack-overview.json`, not from grafana.com), all in
`services/observability/grafana/provisioning/dashboards/json/`. They
show up automatically on first boot and survive a fresh install/wipe,
since they're checked into the repo, not `service_data/`.

**They weren't actually checked in until this pass, despite existing on
disk** — the repo's blanket `*.json` `.gitignore` rule silently excluded
every file in this directory (the `dashboards.yml` provider config right
above it was separately just never `git add`ed at all), so a genuine
fresh clone would have started Grafana with zero dashboards. Fixed with
a `.gitignore` override (`!services/observability/grafana/provisioning/dashboards/json/*.json`,
same pattern `services.json` already uses at repo root) and committing
all three JSON files plus `dashboards.yml` for the first time.

**Stack Overview** answers "how much memory is the whole stack using
right now" in one place instead of reading per-container numbers off
`docker stats`/cadvisor and adding them up by hand: total container
memory (`sum(container_memory_usage_bytes{name!=""})`), host memory
used and used-% (node-exporter — the real ceiling, since it includes
non-container overhead cadvisor's sum doesn't), total container CPU in
cores, and a per-container memory breakdown over time to see which
container is actually driving the total.

`Prometheus`/`Loki` are pinned to fixed datasource UIDs (`prometheus`/
`loki` in `datasources.yml`), and **Stack Overview**'s panels reference
`prometheus` explicitly rather than relying on Grafana's default-
datasource fallback (unlike the other two provisioned dashboards, which
predate this and still omit `datasource` on their panels) — so this
dashboard keeps working even if a second Prometheus datasource is ever
added or `isDefault` changes.

**Upgrading an existing install to a pinned UID is not a hot-reload.**
Grafana 13's apiserver-backed datasource model can't rename an
*already-provisioned* datasource's UID via file provisioning — it
crash-loops instead (`Datasource provisioning error: data source not
found`, container stuck `Restarting`, confirmed live on this repo's own
install). If you're adding `uid:` to a datasource that Grafana has
already provisioned once under an auto-generated UID (i.e. any install
that predates this dashboard), you must wipe Grafana's own state first:
`down observability` (auto-snapshots), delete
`service_data/data/observability/grafana/`, then `up observability` —
dashboards and datasources reprovision from these files with no data
loss, since nothing here is hand-configured through the UI. Skip this
entirely on a genuinely fresh clone; there's nothing to reconcile
against on first boot.

**To update either dashboard later:** re-download the same ID's latest
revision from `https://grafana.com/api/dashboards/<id>/revisions/<rev>/download`
(check the current revision at `https://grafana.com/api/dashboards/<id>/revisions`
first) and overwrite the corresponding JSON file, then
`uv run homeserver.py dev restart observability` — the provisioning
provider (`dashboards.yml`, `updateIntervalSeconds: 30`) also picks up
in-place file changes on its own without a restart, if you'd rather
just edit the file live.

**To add another dashboard:** drop its JSON into the same `json/`
folder — no config changes needed, the provider scans the whole
directory.

## Retention

`PROMETHEUS_RETENTION` (default `15d`) and `LOKI_RETENTION` (default `336h` = 14d) bound how much metrics/log history accumulates — this data isn't regenerable if lost, but unlike a photo library it's not irreplaceable either, so it's kept under `service_data/data/observability/` (backed up on every snapshot) rather than moved to a `cache/` bucket. Lower the retention values if snapshot size becomes a problem; Loki's format must be in hours, Prometheus accepts `Nd`/`Nh` directly.

## Known limitations

- **`cadvisor` runs `privileged: true`** — it needs broad host/cgroup access to read per-container stats; this is the standard cAdvisor deployment shape, not a stack-specific choice, but worth knowing it's the one privileged container in this repo.
- **node-exporter's stats are container-namespace-relative for a few metrics** (notably some network-interface counters) since it's not on `network_mode: host` — CPU/memory/disk are unaffected since `/proc`, `/sys`, and `/` are mounted read-only regardless of network mode.
- **No alerting configured.** Grafana supports alert rules out of the box (Alerting → Alert rules), but none are pre-provisioned — set up rules manually for anything you want paged on (e.g. disk-almost-full, container OOM-looping). SMTP is already wired for when you do: `GRAFANA_SMTP_HOST`/`GRAFANA_SMTP_FROM` in `.env` point Grafana at the shared [Mailpit](mailpit.md) catcher by default (`GF_SMTP_SKIP_VERIFY: "true"` since Mailpit has no TLS at all, not just a self-signed cert) — point them at a real relay instead if you want alert emails to actually leave this host.
- **First boot can exceed `homeserver.py`'s 180s readiness timeout.** Grafana 13's OSS image auto-installs several bundled apps (pyroscope, exploretraces, metricsdrilldown, lokiexplore) on first start, which can push `/api/health` past 180s and print `✖ observability FAILED` even though the container finishes starting and settles into `healthy` a bit later (check with `docker ps` or `dev logs observability`). This only happens once — the plugins land in `${DATA_ROOT}/grafana`, so subsequent `up`/`restart` calls are fast. Safe to ignore on a fresh clone or after wiping `service_data/data/observability/`; no action needed.
- **Loki rejected log lines after ordinary `homeserver.py` restarts** — `"entry too far behind, oldest acceptable timestamp is: ..."` in Alloy/Loki's own logs. Two separate mechanisms reject "old" entries, and fixing only one isn't enough: (1) the distributor-level `reject_old_samples`/`reject_old_samples_max_age` check (default rejects anything over 1 week old — not usually the cause here), and (2) the ingester-level per-stream out-of-order window, sized at **half** of `ingester.max_chunk_age` (default 2h → a 1h window) from that stream's own most recent entry. This stack's normal workflow is frequent `up`/`down`/restart cycles, and Alloy can flush a multi-hour backlog of buffered lines on reconnect after a container's been stopped a while — comfortably wider than the default ~1h window. Fixed in `services/observability/loki/loki-config.yml`: `reject_old_samples: false` plus `ingester.max_chunk_age: 24h`. The risk of accepting genuinely-old data is low for a homelab log store; the cost of silently losing real logs after a routine restart is worse.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
