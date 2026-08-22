# Plane

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Open-source issue tracker and project management.
**Port:** `8100` (host) → `80` (container, `plane-proxy`) | **Data:** `service_data/data/plane/` | **Requires:** Postgres + Redis + RabbitMQ + MinIO, ~4GB RAM minimum / 8GB recommended per Plane's own docs (developers.plane.so) | **Memory:** DB capped 512M in compose.yml; other 10 containers: no hard limit set; measured idle ~709MB total across all 11 containers — `plane-worker` (Celery, 8 prefork processes) is by far the heaviest single container at ~205MB idle, and the one most likely to grow further under real task load

## Setup

```bash
cp services/plane/.env.example services/plane/.env
# generate: openssl rand -hex 32 → SECRET_KEY
# set POSTGRES_PASSWORD, RABBITMQ passwords, MINIO credentials
uv run homeserver.py dev up plane
```

## First login

Browse to `http://<ip>:8100` — create a workspace and admin account.

## Mobile app: not usable against this deployment

Plane's official iOS/Android app requires the self-hosted **Commercial Edition, v1.12.0+** — it explicitly does not support the Community Edition, which is what this stack runs (`makeplane/plane-backend:v1.4.1`, per `compose.yml`). Don't install the mobile app expecting it to work here; the web UI (`https://plane.${DOMAIN}/`) is the only supported client for this deployment. Desktop apps (Mac/Windows/Linux) may have the same CE restriction — check [Plane's current download page](https://plane.so/download) before assuming one works, rather than trusting this note indefinitely as CE/Commercial parity can change release to release.

## Using it day to day

- **Workspace → Project → Issues** is the core hierarchy — a workspace holds multiple projects, each project has its own issue tracker, cycles (sprints), and modules (epics/feature groupings).
- **Cycles** are time-boxed sprints; **Modules** group related issues across cycles (a feature or epic) — use Cycles for "when," Modules for "what."
- Issues support sub-issues, relations (blocks/blocked-by/duplicate), custom states per project, and assignees/labels/priority — configured per-project under project Settings.

## Architecture — needs 5 frontend/backend images, not 3

Multi-container: postgres, valkey, rabbitmq, minio, api, worker, beat, web, admin, space, proxy.

`plane-web` (`makeplane/plane-frontend`) serves the main app **only**. `/god-mode/*` (onboarding, instance admin) and `/spaces/*` (public views) are served by **separate containers**: `plane-admin` (`makeplane/plane-admin`) and `plane-space` (`makeplane/plane-space`).

Routing everything through `plane-web` (as an early version of this setup did) serves the wrong React bundle at those paths — causes a React hydration error (#423) and onboarding buttons that silently do nothing (no request leaves the browser).

The official `Caddyfile` is the source of truth for this routing — extract it from the real proxy image:

```bash
docker run --rm --entrypoint cat makeplane/plane-proxy:v1.4.0 /etc/caddy/Caddyfile
```

It 301-redirects `/god-mode` → `/god-mode/` and `/spaces` → `/spaces/`, then routes each to its own container on port 3000.

## Required env vars

- `SECRET_KEY` (`openssl rand -hex 32`) and all DB/queue passwords in `.env`
- `plane-api` needs `APP_BASE_URL`, `ADMIN_BASE_URL`, `SPACE_BASE_URL` (all `https://plane.${DOMAIN}` in this single-domain setup) **in addition to** `WEB_URL`/`CORS_ALLOWED_ORIGINS` — without them, `GET /api/instances/` returns `null` for those fields

## Operational notes

- `plane-mq` (RabbitMQ) needs `start_period: 90s` on its healthcheck — a fresh vhost/mnesia init can take >30s, especially on a loaded host, and the default was too tight
- After editing `plane/Caddyfile`, run `docker restart plane-proxy` — compose only recreates a container when the *service definition* changes, not when a bind-mounted file's contents change, so editing the Caddyfile alone does **not** reload the proxy

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
