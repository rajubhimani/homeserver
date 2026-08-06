# Coolify

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted PaaS — deploy and manage *other* projects/services with a Vercel/Heroku-style workflow (git push to deploy, one-click databases, etc.).
**Port:** `8132` (host) → `8080` (container); realtime websocket on `6001`/`6002` | **Data:** `service_data/data/coolify/` | **Requires:** Postgres, Redis

## Conceptual overlap worth naming

Coolify's whole purpose is deploying and managing *other* Docker projects on this machine — conceptually it overlaps with what `homeserver.py` already does by hand for this stack. It's included here anyway because it's genuinely useful for deploying separate, unrelated projects (not this repo's own services) through a proper UI/git-push workflow — not to replace `homeserver.py` for managing this stack.

## ⚠ Pinned to an unstable tag — no stable release currently published

As of this writing, `coollabsio/coolify` has **no semver-tagged releases on Docker Hub** (`v4.2.0` etc. return "not found") — only `edge`, `next`, and feature-branch/sha tags exist, an apparent gap in Coolify's release pipeline. This deliberately breaks this stack's usual "always pin a real stable release" rule: `compose.yml` is pinned to `coollabsio/coolify:edge` for now. **Check Docker Hub for a real version tag periodically and switch to it once one exists** — see the corresponding `TODO.md` entry.

## Setup

```bash
cp services/coolify/.env.example services/coolify/.env
# generate ALL secrets before first start (see comments in .env.example) —
# changing any of them later can break the installation
uv run homeserver.py dev up coolify
```

Open `https://coolify.<domain>/` (or `http://<host>:8132` in dev) and complete the first-run setup wizard.

## Registration — a real action item, not just informational

Coolify has no env var for this — public self-registration is **on by default** and stays on until manually disabled in the UI (Settings → Configuration) after your first login. Do this immediately: anyone who finds the URL can otherwise create their own account. Everything else about Coolify's behavior is likewise UI/database-managed, not env-var-driven — there's nothing further to add to `.env` beyond the one-time bootstrap secrets.

## Architecture — 4 containers

- `coolify-db` (Postgres) — app metadata.
- `coolify-redis` — caching/queues.
- `coolify-realtime` (`coollabsio/coolify-realtime`, a maintained Soketi fork) — websocket server for live deploy logs/status in the UI. Listens on `6001` (WS + HTTP API) and `9601` (metrics/`/usage`, used for its own healthcheck — there's no dedicated `/health` path documented).
- `coolify` — the main app; needs the Docker socket mounted (`${DOCKER_SOCKET}`) since its entire job is creating/managing containers on this host for deployed projects, plus several bind-mounted subdirectories (`data`, `ssh`, `applications`, `databases`, `backups`, `services`) that Coolify itself populates.

## Notes

- `APP_ID`/`APP_KEY`/`DB_PASSWORD`/`REDIS_PASSWORD`/`PUSHER_*` are all one-time secrets — generate them once, keep them, never rotate casually (documented upstream behavior: changing them later can break the installation).
- Health endpoint: `/api/health`.
- Since Coolify mounts the Docker socket, treat it with the same trust level as `portainer`/`dockge` in this stack — anything with socket access can affect any other container on the host.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
