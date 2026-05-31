# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A self-hosted personal cloud stack managed with Docker Compose. Each service lives in its own directory with a three-layer compose structure. `homeserver.sh` is the single entrypoint for managing all services.

## Managing services

```bash
# Start / stop services
sh homeserver.sh dev up all
sh homeserver.sh dev up <service>
sh homeserver.sh dev down <service>
sh homeserver.sh prod up all

# Immich with ML (face recognition)
sh homeserver.sh dev up immich --profile ml

# Pull latest images and recreate
sh homeserver.sh dev update all
sh homeserver.sh dev update <service>

# Follow logs
sh homeserver.sh dev logs <service>
```

**Environments:**
- `dev` — ports bound to all interfaces (direct access by IP)
- `prod` — ports bound to `127.0.0.1` only (Nginx Proxy Manager handles external access)

**Service groups:**
- `all` — full startup/shutdown sequence
- `core` — dozzle, nginx, landing, nextcloud only
- Manual-only (not in `all`): `stirling-pdf`, `wg-easy`, `headscale`, `openvpn`, `portainer`, `dockge`

**Startup order:** dozzle → nginx → landing → nextcloud → vaultwarden → gitea → forgejo → immich → jellyfin → paperless → stirling-pdf-lite → mealie → uptime-kuma

## Compose file pattern

Every service follows the same three-file pattern:

| File | Purpose |
| --- | --- |
| `compose.yml` | Base: images, env, volumes, networks — no ports |
| `compose.dev.yml` | Adds ports on all interfaces (`0.0.0.0:HOST:CONTAINER`) |
| `compose.prod.yml` | Adds ports on loopback only (`127.0.0.1:HOST:CONTAINER`) |

`homeserver.sh` merges `compose.yml` + the env-specific override automatically. `landing/` is the exception — it uses `docker-compose.yml` as the base filename.

All services join the external `homeserver` Docker bridge network. NPM resolves services by container name within this network.

## Adding a new service

1. Create `<service>/compose.yml`, `compose.dev.yml`, `compose.prod.yml`, `.env`, and `.env.example`
2. Set `DATA_ROOT=../service_data/<service>` in both `.env` and `.env.example`
3. Create `service_data/<service>/` subdirectories before first start (see Data directory convention below)
4. Add the service name to `SERVICES_UP` and `SERVICES_DOWN` in `homeserver.sh`
5. Add a card to `landing/index.html` under the appropriate section
6. Add NPM proxy host entry in `docs/11-services-reference.md`
7. Add a service row in `docs/11-services-reference.md` and `setup.md`
8. Document setup steps in `docs/10-new-services.md`

## Services with PostgreSQL

Services that need Postgres (nextcloud, paperless, mealie, gitea, forgejo) include:
- `forgejo-db` / `gitea-db` / etc. container using `postgres:18`
- `postgres-init/init.sh` that grants schema ownership — required due to PostgreSQL 15+ default privilege changes
- Healthcheck on the DB so the app container waits until it's ready
- Postgres data volume path: `${DATA_ROOT}/<service>/postgres:/var/lib/postgresql/data`

## Traffic flow

```
Browser → Cloudflare Edge (TLS) → cloudflared → NPM:80 → <container>
```

Cloudflare terminates TLS. Internal traffic is plain HTTP. NPM proxy hosts use `http` scheme and the Docker container name as the forward hostname.

## Port reference

| Service | Dev port | Container port |
| --- | --- | --- |
| Nginx Proxy Manager | 80 / 443 | 80 / 443 |
| Landing | 8082 | 80 |
| Dozzle | 9999 | 8080 |
| Nextcloud | 8081 | 80 |
| Immich | 2283 | 2283 |
| Jellyfin | 8096 | 8096 |
| Vaultwarden | 8200 | 80 |
| Paperless | 8010 | 8000 |
| Stirling PDF Lite | 8090 | 8080 |
| Stirling PDF (Full) | 8089 | 8080 |
| Mealie | 9000 | 9000 |
| Gitea | 3000 / 2222 | 3000 / 22 |
| Forgejo | 3001 / 2223 | 3000 / 22 |
| Uptime Kuma | 3001 | 3001 |

## Data directory convention

All persistent service data lives under a single `service_data/` directory at the repo root, with one subfolder per service:

```
service_data/        ← gitignored entirely
  forgejo/
    postgres/        ← DB files
    app/             ← app data
  gitea/
    postgres/
    data/
  nextcloud/
    ...
```

- **Always set** `DATA_ROOT=../service_data/<service>` in the service's `.env`
- **Always create** the subdirectories before first start:
  ```bash
  mkdir -p service_data/<service>/postgres service_data/<service>/app
  ```
- Volume paths in `compose.yml` use `${DATA_ROOT}/postgres`, `${DATA_ROOT}/app`, etc. — no service name prefix needed
- `service_data/` is in `.gitignore` — never committed
- `homeserver.sh` always injects `DATA_ROOT` as an absolute path (`$BASE_DIR/service_data/<service>`) overriding the `.env` value — so the `.env` relative path is only a fallback for running `docker compose` directly
- On the production Linux server, point `DATA_ROOT` at the external drive instead (e.g. `/mnt/seagate/forgejo`)

## Key service notes

- **Nextcloud**: uses partial volume mounts — do not mount full `/var/www/html`. Has a `before-starting` hook that runs rsync on startup.
- **Immich**: uses a custom Postgres image with pgvector (`ghcr.io/immich-app/postgres`). ML profile is opt-in.
- **Stirling PDF**: Lite (`latest-ultra-lite`) is always on; Full (`latest`) is manual-only due to ~1.5GB RAM usage.
- **Forgejo**: image `codeberg.org/forgejo/forgejo:15`. Config env vars use `FORGEJO__` prefix. SSH on host port 2223. Setup wizard skipped via `FORGEJO__security__INSTALL_LOCK=true`.
- **Gitea**: config env vars use `GITEA__` prefix. SSH on host port 2222. Setup wizard skipped via `GITEA__security__INSTALL_LOCK=true`.
- **Vaultwarden**: signups disabled by default (`SIGNUPS_ALLOWED=false`); invite users via `/admin` panel.

## Registration toggle per service

Each service with public signup has a toggle in its `.env`:

| Service | Env var | Disable value | Allow value |
| --- | --- | --- | --- |
| Forgejo | `DISABLE_REGISTRATION` | `true` | `false` |
| Gitea | `DISABLE_REGISTRATION` | `true` | `false` |
| Vaultwarden | `SIGNUPS_ALLOWED` | `false` | `true` |
| Mealie | `ALLOW_SIGNUP` | `false` | `true` |

All default to **disabled**. To re-enable, update the value in `.env` and restart the service:
```bash
sh homeserver.sh dev up <service>
```

Services with no public signup (Nextcloud, Immich, Paperless, Jellyfin, Uptime Kuma) are always admin-managed — no toggle needed.
