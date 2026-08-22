# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Keep this file **small** — it's an index of core facts and where to look, not a place to inline procedures. Detailed how-tos live in skills (`.claude/skills/`) that get pulled in only when the matching task is actually in progress; per-service detail lives in `docs/services/<service>.md`.

## What this repo is

A self-hosted personal cloud stack managed with Docker Compose. Each service lives in its own directory under `services/` (e.g. `services/nextcloud/`) with a three-layer compose structure (`compose.yml` base + `compose.dev.yml`/`compose.prod.yml` overrides — see "Compose file pattern" below). `homeserver.py` is the single entrypoint for managing all services — run it with `uv run homeserver.py ...` (requires [uv](https://docs.astral.sh/uv/); `uv sync` once) or plain `python`/`python3 homeserver.py ...` if you manage Python yourself. Pure-stdlib by default; see the `homeserver-docker-backend` skill for the optional `python-on-whales` backend and Windows-specific notes.

There is no shell-script entrypoint — an earlier `homeserver.sh` was retired once `homeserver.py` reached full feature parity. Don't recreate one; that's a deliberate new decision to make with the user, not a default to fall back to.

**Any change to a service's `.env` or `compose.yml` must land hand-in-hand with `.env.example` and `docs/services/<service>.md` in the same pass, never as a follow-up.** A code change that "works" but leaves `.env.example` stale (breaks a fresh clone) or the doc stale (silently wrong reference material) is not done — treat it the same as a missing test. This applies to every `.env`/compose edit, not just new-service setup or the specific pattern the `homeserver-add-service` skill walks through.

## Global configuration

Set your domain and runtime once in the root `.env` — `homeserver.py` injects them into every service automatically:

```bash
# .env (repo root)
DOMAIN=yourdomain.com
RUNTIME=docker                              # 'docker' (default) or 'podman'
DOCKER_SOCKET=/var/run/docker.sock          # rootless podman: /run/user/1000/podman/podman.sock
BACKUP_RETENTION=5                          # snapshots kept per service, -1 = unlimited
```

`homeserver.py` also injects `DATA_ROOT` per service (never hardcode the domain in individual service `.env` files — use `${DOMAIN}`). **Some services have a second, independent `service_data/`-pointing env var that is *not* auto-injected** (e.g. immich's `UPLOAD_LOCATION`, jellyfin's `MEDIA_ROOT`, dockge's `DOCKGE_STACKS_DIR`) — see the `homeserver-add-service` skill for the grep-everything rule this implies if `service_data/` paths are ever restructured.

Services that mount the container socket (dozzle, portainer, dockge, gitlab, authentik) use `${DOCKER_SOCKET}`. Forgejo's CI runner deliberately does *not* — it uses an isolated Docker-in-Docker sidecar instead so CI jobs never touch this host's real Docker; see `docs/services/forgejo.md`.

## Managing services

```bash
# Tiers — MIN ⊂ CORE ⊂ DAILY ⊂ OFFICE ⊂ AUTOMATION-AI ⊂ ALL
uv run homeserver.py dev up min          # up/down/restart/update all take the same targets
uv run homeserver.py dev up core         # bootstraps min if not already running
uv run homeserver.py dev up daily        # opt-in — bootstraps min/core if needed, NOT implied by 'up core'
uv run homeserver.py dev up office       # opt-in — bootstraps min/core/daily if needed, NOT implied by 'up daily'
uv run homeserver.py dev up automation-ai # opt-in — bootstraps min/core/daily/office if needed, NOT implied by 'up office'
uv run homeserver.py dev up all
uv run homeserver.py dev down core       # stops ONLY core — min stays running
uv run homeserver.py dev down daily      # stops ONLY daily — min/core stay running
uv run homeserver.py dev down office     # stops ONLY office — min/core/daily stay running
uv run homeserver.py dev down automation-ai # stops ONLY automation-ai — min/core/daily/office stay running
uv run homeserver.py dev down all        # reverse order, always complete — the one command that stops everything

uv run homeserver.py dev up <service>    # single or multiple services
uv run homeserver.py dev logs <service>
uv run homeserver.py dev update running  # only currently running services
uv run homeserver.py dev up immich --profile ml
uv run homeserver.py prod up all         # prod = ports on 127.0.0.1 only
```

Backups/restore/snapshots: see the `homeserver-backups` skill (short version: `down` auto-snapshots every time, `--no-backup` to skip; `up` auto-restores the latest snapshot if a service's volumes/data are both missing, `--fresh` to skip).

**Service tiers (additive):**

- **SERVICES_MIN** (infrastructure): beszel → cloudflared → nginx-plain → landing → docs → portainer
- **SERVICES_CORE** (always-on apps, on top of MIN): observability → plausible → mailpit → nextcloud → vaultwarden → forgejo → firefly → immich → jellyfin → guacamole → it-tools → authentik → atuin → adguard-home
- **SERVICES_DAILY** (regular-use apps, opt-in — `up daily` or `up all`, never implied by `up core`): firefox → chromium → ungoogled-chromium → brave → mullvad-browser → uptime-kuma → syncthing → trilium → silverbullet → excalidraw → karakeep → wallabag → coolify → homebox
- **SERVICES_OFFICE** (firm/business apps, opt-in — `up office` or `up all`, never implied by `up daily`): stirling-pdf-lite → stirling-pdf → miniflux → appflowy → plane → vikunja → listmonk → calcom
- **SERVICES_AUTOMATION_AI** (workflow/automation/AI apps, opt-in — `up automation-ai` or `up all`, never implied by `up office`): ollama → open-webui → n8n → airflow → temporal → dagster
- **SERVICES_EXTRA** (`up all` or individually): dozzle → dockge → openproject → paperless → mealie → audiobookshelf → invoiceshelf → outline → bookstack → mattermost → rocketchat → zulip → ntfy → crowdsec → orangehrm → nocodb → documenso → penpot → supabase
- **SERVICES_MANUAL** (never auto-started by any tier — `up <service>` only): gitlab (redundant with forgejo, far higher memory)

**`services.json`** (repo root) is the actual source of truth for the lists above — `homeserver.py` derives `SERVICES_MIN`/`SERVICES_CORE`/`SERVICES_DAILY`/`SERVICES_OFFICE`/`SERVICES_AUTOMATION_AI`/`SERVICES_EXTRA`/`SERVICES_MANUAL` from its `tier` field, and `services/landing/index.html` fetches the same file at page load for its category/subcategory cards, so a service's tier and its landing metadata can never drift apart. Re-check `services.json` (not this file) if the summary above ever looks stale.

Every `category`/`subcategory` value in `services.json` is also a startable group: `up group:<name>` (works with every action — `down`/`restart`/`update`/etc.) starts every service sharing that category or subcategory, e.g. `up group:notes` or `up group:productivity`.

Adding or moving a service between tiers, wiring up a new service end-to-end (landing page, health route, docs, ports): **see the `homeserver-add-service` skill.**

## Compose file pattern

| File | Purpose |
| --- | --- |
| `compose.yml` | Base: images, env, volumes, networks — no ports |
| `compose.dev.yml` | Adds ports on all interfaces (`0.0.0.0:HOST:CONTAINER`) |
| `compose.prod.yml` | Adds ports on loopback only (`127.0.0.1:HOST:CONTAINER`) |

`homeserver.py` merges `compose.yml` + the env-specific override automatically. `landing/` is the exception — it uses `docker-compose.yml` as the base filename. All services join the external `homeserver` Docker bridge network; proxies resolve services by container name on it.

## Data directory convention

All persistent data lives under `service_data/` at the repo root (gitignored entirely, a sibling of `services/`), split into `data/` (live, bind-mounted) and `backup/` (timestamped snapshots — see `homeserver-backups` skill). Set `DATA_ROOT=../../service_data/data/<service>` in the service's `.env` (two levels up — `services/<service>/.env` to repo root); `homeserver.py` overrides it with an absolute path at runtime. DB data (Postgres/MariaDB/Redis-persisted/RabbitMQ) is a **named Docker volume**, not under `data/` at all — see the `homeserver-postgres` skill for why and how.

**Never delete anything under `service_data/data/`** — it's always live. Snapshots under `service_data/backup/<service>/<timestamp>/` are safe to delete individually.

## Where to look for everything else

| Topic | Where |
| --- | --- |
| Adding a new service end-to-end, registration toggles, healthcheck patterns | `homeserver-add-service` skill |
| Postgres/MariaDB setup, named-volume rules, memory tuning, immich-db quirks | `homeserver-postgres` skill |
| `homeserver.py`'s `DockerBackend` abstraction, Windows/WSL2 notes | `homeserver-docker-backend` skill |
| Reverse proxy (nginx-plain vs NPM), traffic flow, `X-Forwarded-Proto` | `homeserver-reverse-proxy` skill |
| Backup/restore/snapshots, machine migration | `homeserver-backups` skill |
| Port numbers, service tiers, NPM proxy-host table (canonical, keep this one updated) | [`docs/11-services-reference.md`](docs/11-services-reference.md) |
| Per-service setup, architecture, every gotcha/troubleshooting note | [`docs/services/<service>.md`](docs/services/) — one consolidated doc per service |
| Kubernetes pilot (parallel to Compose, not a replacement — see `feature/k8s-pilot` branch) | [`kubernetes/README.md`](kubernetes/README.md) for setup/status, [`kubernetes/TROUBLESHOOTING.md`](kubernetes/TROUBLESHOOTING.md) for every gotcha hit so far (incl. disk-full recovery, ArgoCD bootstrap, Compose-vs-k8s semantic traps) |
| Capping Docker's total CPU/memory/disk usage on the host (Fedora/Ubuntu/Windows) | [`docker/README.md`](docker/README.md) — separate from any service's own `deploy.resources.limits`, this caps the whole engine |
