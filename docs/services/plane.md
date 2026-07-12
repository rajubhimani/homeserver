# Plane

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Open-source issue tracker and project management.
**Port:** `8100` (host) → `80` (container, `plane-proxy`) | **Data:** `service_data/data/plane/` | **Requires:** ~4 GB RAM

## Setup

```bash
cp plane/.env.example plane/.env
# generate: openssl rand -hex 32 → SECRET_KEY
# set POSTGRES_PASSWORD, RABBITMQ passwords, MINIO credentials
uv run homeserver.py dev up plane
```

## First login

Browse to `http://<ip>:8100` — create a workspace and admin account.

## Architecture — needs 5 frontend/backend images, not 3

Multi-container: postgres, valkey, rabbitmq, minio, api, worker, beat, web, admin, space, proxy.

`plane-web` (`makeplane/plane-frontend`) serves the main app **only**. `/god-mode/*` (onboarding, instance admin) and `/spaces/*` (public views) are served by **separate containers**: `plane-admin` (`makeplane/plane-admin`) and `plane-space` (`makeplane/plane-space`).

Routing everything through `plane-web` (as an early version of this setup did) serves the wrong React bundle at those paths — causes a React hydration error (#423) and onboarding buttons that silently do nothing (no request leaves the browser).

The official `Caddyfile` is the source of truth for this routing — extract it from the real proxy image:

```bash
docker run --rm --entrypoint cat makeplane/plane-proxy:v1.3.1 /etc/caddy/Caddyfile
```

It 301-redirects `/god-mode` → `/god-mode/` and `/spaces` → `/spaces/`, then routes each to its own container on port 3000.

## Required env vars

- `SECRET_KEY` (`openssl rand -hex 32`) and all DB/queue passwords in `.env`
- `plane-api` needs `APP_BASE_URL`, `ADMIN_BASE_URL`, `SPACE_BASE_URL` (all `https://plane.${DOMAIN}` in this single-domain setup) **in addition to** `WEB_URL`/`CORS_ALLOWED_ORIGINS` — without them, `GET /api/instances/` returns `null` for those fields

## Operational notes

- `plane-mq` (RabbitMQ) needs `start_period: 60s` on its healthcheck — a fresh vhost/mnesia init can take >30s, especially on a loaded host, and the default was too tight
- After editing `plane/Caddyfile`, run `docker restart plane-proxy` — compose only recreates a container when the *service definition* changes, not when a bind-mounted file's contents change, so editing the Caddyfile alone does **not** reload the proxy

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
