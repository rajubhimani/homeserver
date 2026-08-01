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
cp observability/.env.example observability/.env
# set GRAFANA_ADMIN_PASSWORD to something real — the example default is a placeholder
uv run homeserver.py dev up observability
```

Grafana admin login is `${GRAFANA_ADMIN_USER}` / `${GRAFANA_ADMIN_PASSWORD}` from `.env` (defaults to `admin`). No public signup — `GF_USERS_ALLOW_SIGN_UP` is hardcoded `false` in `compose.yml`, matching Grafana's own default; this is an admin-provisioned dashboard, not a service with real end users.

Prometheus and Loki dashboards ship empty — Grafana's own "Docker" and "Node Exporter Full" community dashboards (importable by ID from grafana.com, e.g. `1860` for Node Exporter Full, `19792` for a cAdvisor/Docker overview) are a reasonable starting point rather than building panels from scratch.

## Retention

`PROMETHEUS_RETENTION` (default `15d`) and `LOKI_RETENTION` (default `336h` = 14d) bound how much metrics/log history accumulates — this data isn't regenerable if lost, but unlike a photo library it's not irreplaceable either, so it's kept under `service_data/data/observability/` (backed up on every snapshot) rather than moved to a `cache/` bucket. Lower the retention values if snapshot size becomes a problem; Loki's format must be in hours, Prometheus accepts `Nd`/`Nh` directly.

## Known limitations

- **`cadvisor` runs `privileged: true`** — it needs broad host/cgroup access to read per-container stats; this is the standard cAdvisor deployment shape, not a stack-specific choice, but worth knowing it's the one privileged container in this repo.
- **node-exporter's stats are container-namespace-relative for a few metrics** (notably some network-interface counters) since it's not on `network_mode: host` — CPU/memory/disk are unaffected since `/proc`, `/sys`, and `/` are mounted read-only regardless of network mode.
- **No alerting configured.** Grafana supports alert rules out of the box (Alerting → Alert rules), but none are pre-provisioned — set up rules manually for anything you want paged on (e.g. disk-almost-full, container OOM-looping).
- **First boot can exceed `homeserver.py`'s 180s readiness timeout.** Grafana 13's OSS image auto-installs several bundled apps (pyroscope, exploretraces, metricsdrilldown, lokiexplore) on first start, which can push `/api/health` past 180s and print `✖ observability FAILED` even though the container finishes starting and settles into `healthy` a bit later (check with `docker ps` or `dev logs observability`). This only happens once — the plugins land in `${DATA_ROOT}/grafana`, so subsequent `up`/`restart` calls are fast. Safe to ignore on a fresh clone or after wiping `service_data/data/observability/`; no action needed.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
