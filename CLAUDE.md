# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A self-hosted personal cloud stack managed with Docker Compose. Each service lives in its own directory with a three-layer compose structure. `homeserver.sh` is the single entrypoint for managing all services.

## Global configuration

Set your domain and runtime once in the root `.env` — `homeserver.sh` injects them into every service automatically:

```bash
# .env (repo root)
DOMAIN=yourdomain.com

# Container runtime: 'docker' (default) or 'podman'
RUNTIME=docker

# Socket path — change for Podman:
#   rootful:  /run/podman/podman.sock
#   rootless: /run/user/1000/podman/podman.sock
DOCKER_SOCKET=/var/run/docker.sock
```

`homeserver.sh` also injects `DATA_ROOT` per service. Never hardcode the domain in individual service `.env` files — use `${DOMAIN}` references where possible.

Services that mount the container socket (dozzle, portainer, dockge, gitea, forgejo, gitlab, authentik) use `${DOCKER_SOCKET}` — set it in the root `.env` to switch between Docker and Podman sockets.

## Managing services

```bash
# Tiers — MIN ⊂ CORE ⊂ ALL
sh homeserver.sh dev up min          # bare minimum: dozzle, nginx-plain, landing
sh homeserver.sh dev up core         # full default stack
sh homeserver.sh dev up all          # everything (core + extra)
sh homeserver.sh dev down min        # stop min (reverse order)
sh homeserver.sh dev down core       # stop core (reverse order)
sh homeserver.sh dev down all        # stop everything (reverse order, always complete)

# Single service or multiple
sh homeserver.sh dev up <service>
sh homeserver.sh dev down <service>
sh homeserver.sh prod up all

# Immich with ML (face recognition)
sh homeserver.sh dev up immich --profile ml

# Pull latest images and recreate
sh homeserver.sh dev update all
sh homeserver.sh dev update running  # only currently running services
sh homeserver.sh dev update <service>

# Follow logs
sh homeserver.sh dev logs <service>
```

**Environments:**

- `dev` — ports bound to all interfaces (direct access by IP)
- `prod` — ports bound to `127.0.0.1` only (Nginx Proxy Manager handles external access)

**Service tiers (additive — each builds on the previous):**

| Tier | Command | Contains | Use for |
| --- | --- | --- | --- |
| `min` | `up min` | infrastructure only | bare minimum to serve anything |
| `core` | `up core` | min + always-on apps | standard daily use |
| `all` | `up all` | min + core + extra | everything |

- `down all` always stops every tier in reverse order — automatically complete, no list to maintain

**IMPORTANT — adding a new service:**

- **Always add to `SERVICES_EXTRA` first** — never directly to `SERVICES_MIN` or `SERVICES_CORE`
- Only move to `SERVICES_CORE` when explicitly asked (service confirmed stable and always-on)
- Only move to `SERVICES_MIN` for pure infrastructure (reverse proxy, tunnel, log viewer)
- Never maintain a separate `SERVICES_DOWN` list — shutdown order is computed by reversing `MIN + CORE + EXTRA`

**SERVICES_MIN (infrastructure):** dozzle → cloudflared → nginx-plain → landing

**SERVICES_CORE (always-on apps, added on top of MIN):** nextcloud

**SERVICES_EXTRA (optional — start with `up all` or individually):** vaultwarden → gitea → forgejo → gitlab → immich → jellyfin → paperless → stirling-pdf-lite → mealie → uptime-kuma → … (all other services)

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
   - If the service mounts host paths or the Docker socket, also create `compose.podman.yml` with `security_opt: label=disable` (SELinux fix for Podman)
2. Set `DATA_ROOT=../service_data/<service>` in **both** `.env` and `.env.example`
3. Every env var added to `.env` must also be added to `.env.example` with its default value and a comment — they must always stay in sync
4. If the service supports registration control, always add the appropriate toggle to both `.env` and `.env.example` (see Registration toggle table below)
5. Create `service_data/<service>/` subdirectories before first start (see Data directory convention below)
6. Add the service name to `SERVICES_EXTRA` in `homeserver.sh` — always extra first, move to `SERVICES_CORE` only when explicitly asked; `down all` derives shutdown order automatically
7. Add a card to `landing/index.html` under the appropriate section and add its subdomain to `SERVICE_SUBDOMAINS` in the script block
8. Add a `/health/<service>` proxy route to `landing/nginx.conf` pointing to `http://<container>:<port>` — without this the landing page card always shows offline
9. Add NPM proxy host entry in `docs/11-services-reference.md`
10. Add a service row in `docs/11-services-reference.md` and `setup.md`
11. Document setup steps in `docs/10-new-services.md`
12. Add a `healthcheck` to the service container in `compose.yml` (see healthcheck patterns below)
13. If the service has optional sub-services (e.g. runners added via `--profile`), document them in **all** relevant doc sections in the same pass — never update compose files without updating the matching docs
14. Every service container must have a `healthcheck` — use the service's own health endpoint where available, otherwise a simple HTTP probe or process check. This enables reliable `depends_on: condition: service_healthy` ordering and makes `docker ps` show real status

**Healthcheck patterns by service type:**

- nginx-based: `wget -q --spider http://localhost/ || exit 1`
- HTTP app: `curl -f http://localhost:<port>/health || exit 1`
- Dozzle: `["/dozzle", "healthcheck"]`
- Gitea/Forgejo: `curl -f http://localhost:3000/api/healthz || exit 1`
- Nextcloud: `curl -f http://localhost/status.php || exit 1`
- Postgres: `pg_isready -U ${POSTGRES_USER}`
- Redis/Valkey: `redis-cli ping` / `valkey-cli ping`

## Services with PostgreSQL

Services that need Postgres (nextcloud, paperless, mealie, gitea, forgejo) include:

- `forgejo-db` / `gitea-db` / etc. container using `postgres:18`
- `postgres-init/init.sh` that grants schema ownership — required due to PostgreSQL 15+ default privilege changes
- Healthcheck on the DB so the app container waits until it's ready
- Postgres data volume path: `${DATA_ROOT}/postgres:/var/lib/postgresql`

## Reverse proxy — pick one

Two options — **run only one at a time**, both bind to port 80/443:

| Option | Service | Best for |
| --- | --- | --- |
| `nginx-plain` | Plain nginx | **Default** — config-file based, domain-templated, works with Cloudflare Tunnel |
| `nginx` | Nginx Proxy Manager | Optional — UI-based config, Let's Encrypt via UI |

**To switch to NPM:** replace `nginx-plain` with `nginx` in `SERVICES_UP` in `homeserver.sh`. Then edit `nginx-plain/conf.d/default.conf` — replace `yourdomain.com` with your domain.

## Traffic flow

```text
Browser → Cloudflare Edge (TLS) → cloudflared (container) → nginx / NPM :80 → <container>
```

Cloudflare terminates TLS. Internal traffic is plain HTTP. Both proxies resolve services by Docker container name on the `homeserver` network. `cloudflared` connects **outbound only** — no ports need to be opened on the firewall.

## Port reference

**IMPORTANT — always check this table before assigning ports to a new service. Every host dev port must be unique. SSH ports must also be unique.**

| Service | Dev port | Container port |
| --- | --- | --- |
| Nginx Proxy Manager | 80 / 443 | 80 / 443 |
| Nginx Plain (dev) | 8180 / 8443 | 80 / 443 |
| Landing | 8080 | 80 |
| Dozzle | 9999 | 8080 |
| Nextcloud | 8081 | 80 |
| Immich | 2283 | 2283 |
| Jellyfin | 8096 | 8096 |
| Vaultwarden | 8200 | 80 |
| Paperless | 8010 | 8000 |
| Stirling PDF Lite | 8090 | 8080 |
| Stirling PDF (Full) | 8089 | 8080 |
| Mealie | 9925 | 9000 |
| Gitea | 3000 / 2222 (SSH) | 3000 / 22 |
| Forgejo | 3002 / 2223 (SSH) | 3000 / 22 |
| GitLab | 8085 / 2224 (SSH) | 80 / 22 |
| Uptime Kuma | 3001 | 3001 |
| Headscale | 8086 | 8080 |
| Syncthing | 8087 | 8384 |
| Authentik | 8088 | 9000 |
| Stalwart Mail | 8091 | 8080 |
| Ntfy | 8092 | 80 |
| Miniflux | 8093 | 8080 |
| Audiobookshelf | 8094 | 80 |
| Conduit (Matrix) | 8095 / 8448 (federation) | 6167 |
| Snappymail | 8097 | 8888 |
| Roundcube | 8098 | 80 |
| OpenProject | 8099 | 80 |
| Plane | 8100 | 80 |
| Crater | 8101 | 80 |

**Next available ports:** web `8102`, SSH `2225`

When adding a new service:

- Pick a web port not in the table above — update this table immediately
- If the service has SSH, pick the next SSH port (`2225`, `2226`, …)
- Never reuse a port, even for manual-only services — they may run alongside `all`

## Data directory convention

All persistent service data lives under a single `service_data/` directory at the repo root, with one subfolder per service:

```text
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
| GitLab | `SIGNUP_ENABLED` | `false` | `true` |

All default to **disabled**. To re-enable, update the value in `.env` and restart the service:

```bash
sh homeserver.sh dev up <service>
```

Services with no public signup (Nextcloud, Immich, Paperless, Jellyfin, Uptime Kuma) are always admin-managed — no toggle needed.
