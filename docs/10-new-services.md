# 10 — New Services

[← Firewall](09-firewall.md) | [Home](../setup.md)

---

All services follow the same three-file compose pattern:

- `compose.yml` — base config, no ports
- `compose.dev.yml` — ports on all interfaces (direct access)
- `compose.prod.yml` — ports on `127.0.0.1` only (nginx proxy handles external)
- `.env` — secrets and paths (copy from `.env.example`)

Use `homeserver.sh` to manage them (see [Maintenance](08-maintenance.md)).

---

## Jellyfin

**Purpose:** Stream movies, TV shows, and music from your server.  
**Port:** `8096`  
**Data:** `service_data/jellyfin/`

```bash
cp jellyfin/.env.example jellyfin/.env
# edit .env — set MEDIA_ROOT to your media drive path
```

```env
DATA_ROOT=../service_data/jellyfin
MEDIA_ROOT=/mnt/seagate/media
```

```bash
sh homeserver.sh dev up jellyfin
```

**Admin account:**

| Method | How |
| --- | --- |
| First visit | Open `http://<ip>:8096` — setup wizard creates the admin account |

---

## Vaultwarden

**Purpose:** Self-hosted password manager, compatible with all Bitwarden apps.  
**Port:** `8200`  
**Data:** `service_data/vaultwarden/`

```bash
cp vaultwarden/.env.example vaultwarden/.env
# edit .env
```

```env
DATA_ROOT=../service_data/vaultwarden
VAULTWARDEN_DOMAIN=https://vault.yourdomain.com
ADMIN_TOKEN=<openssl rand -base64 48>
SIGNUPS_ALLOWED=false
```

```bash
sh homeserver.sh dev up vaultwarden
```

**Admin access:** Vaultwarden has no admin user account — the admin panel is protected by `ADMIN_TOKEN`.

| Method | How |
| --- | --- |
| Admin panel | `http://<ip>:8200/admin` → enter `ADMIN_TOKEN` |

**Inviting users (no SMTP needed):**

1. Admin panel → Users → Invite User → enter email
2. Share `http://<ip>:8200/#/signup` with the invited email address

---

## Paperless-ngx

**Purpose:** Scan, OCR, and archive documents. Full-text search.  
**Port:** `8010`  
**Data:** `service_data/paperless/`  
**Depends on:** Postgres + Redis (included in compose)

```bash
cp paperless/.env.example paperless/.env
# edit .env
```

```env
DATA_ROOT=../service_data/paperless
TZ=Asia/Kolkata
POSTGRES_DB=paperless
POSTGRES_USER=paperless
POSTGRES_PASSWORD=your_strong_password
PAPERLESS_SECRET_KEY=<openssl rand -hex 32>
PAPERLESS_URL=http://192.168.1.100:8010
PAPERLESS_ADMIN_USER=admin
PAPERLESS_ADMIN_PASSWORD=your_strong_password
```

```bash
sh homeserver.sh dev up paperless
```

**Admin account:**

| Method | How |
| --- | --- |
| Env vars ✓ | `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` — auto-created on first start |
| CLI | `docker exec -it paperless python manage.py createsuperuser` |

---

## Stirling PDF Lite

**Purpose:** Lightweight PDF toolkit — always on, default endpoint.  
**Port:** `8090`  
**Image:** `stirlingtools/stirling-pdf:latest-ultra-lite` (~200MB)  
**Data:** `service_data/stirling-pdf-lite/`

```bash
cp stirling-pdf-lite/.env.example stirling-pdf-lite/.env
# edit .env — set password
```

```env
DATA_ROOT=../service_data/stirling-pdf-lite
STIRLING_ADMIN_USER=admin
STIRLING_ADMIN_PASSWORD=your_strong_password
```

```bash
sh homeserver.sh dev up stirling-pdf-lite
```

**Admin account:**

| Method | How |
| --- | --- |
| Env vars ✓ | `STIRLING_ADMIN_USER` / `STIRLING_ADMIN_PASSWORD` — set at startup |

---

## Stirling PDF (Full)

**Purpose:** Full PDF toolkit with OCR, LibreOffice conversion — manual start only (heavy).  
**Port:** `8089`  
**Image:** `stirlingtools/stirling-pdf:latest` (~1.5GB)  
**Data:** `service_data/stirling-pdf/`

> Not in `all` — start manually when needed, stop when done.

```bash
sh homeserver.sh dev up stirling-pdf
sh homeserver.sh dev down stirling-pdf
```

**Admin account:** No login required — all processing is local.

---

## Mealie

**Purpose:** Recipe manager and meal planner.  
**Port:** `9000`  
**Data:** `service_data/mealie/`  
**Depends on:** Postgres (included in compose)

```bash
cp mealie/.env.example mealie/.env
# edit .env
```

```env
DATA_ROOT=../service_data/mealie
POSTGRES_DB=mealie
POSTGRES_USER=mealie
POSTGRES_PASSWORD=your_strong_password
MEALIE_BASE_URL=https://mealie.yourdomain.com
ALLOW_SIGNUP=false
```

```bash
sh homeserver.sh dev up mealie
```

**Admin account:**

| Method | How |
| --- | --- |
| Default credentials | `changeme@example.com` / `MyPassword` — **change immediately** after first login |

---

## Gitea

**Purpose:** Self-hosted Git service. Manage repos, issues, pull requests.  
**Port:** `3000` (web), `2222` (SSH)  
**Data:** `service_data/gitea/`  
**Depends on:** Postgres (included in compose)

```bash
cp gitea/.env.example gitea/.env
# edit .env
```

```env
DATA_ROOT=../service_data/gitea
POSTGRES_DB=gitea
POSTGRES_USER=gitea
POSTGRES_PASSWORD=your_strong_password
GITEA_DOMAIN=gitea.yourdomain.com
GITEA_ROOT_URL=https://gitea.yourdomain.com
DISABLE_REGISTRATION=true
GITEA_RUNNER_TOKEN=your_runner_token_here
```

```bash
sh homeserver.sh dev up gitea
```

**Admin account:**

| Method | How |
| --- | --- |
| CLI ✓ | `docker exec -it gitea gitea admin user create --username admin --password yourpassword --email admin@example.com --admin` |
| First visit | Remove `GITEA__security__INSTALL_LOCK: "true"` from `compose.yml`, restart, browse to `http://<ip>:3000` — setup wizard appears with an admin form at the bottom |

**Actions runner (optional):**

1. Site Admin → Runners → Create Runner → copy the token
2. Set `GITEA_RUNNER_TOKEN=<token>` in `.env`
3. `sh homeserver.sh dev up gitea --profile runner`

---

## Forgejo

**Purpose:** Community-driven Gitea fork. Self-hosted Git with repos, CI/CD actions, and issue tracking.  
**Port:** `3001` (web), `2223` (SSH)  
**Data:** `service_data/forgejo/`  
**Depends on:** Postgres (included in compose)

```bash
cp forgejo/.env.example forgejo/.env
# edit .env
```

```env
DATA_ROOT=../service_data/forgejo
POSTGRES_DB=forgejo
POSTGRES_USER=forgejo
POSTGRES_PASSWORD=your_strong_password
FORGEJO_DOMAIN=forgejo.yourdomain.com
FORGEJO_ROOT_URL=https://forgejo.yourdomain.com
DISABLE_REGISTRATION=false
```

```bash
sh homeserver.sh dev up forgejo
```

**Admin account:**

| Method | How |
| --- | --- |
| CLI ✓ | `docker exec -it forgejo forgejo admin user create --username admin --password yourpassword --email admin@example.com --admin` |
| First visit | Remove `FORGEJO__security__INSTALL_LOCK: "true"` from `compose.yml`, restart, browse to `http://<ip>:3001` — setup wizard appears with an admin form at the bottom |

**Actions runner (optional):**

```bash
sh homeserver.sh dev up forgejo --profile runner
docker exec -it forgejo-runner forgejo-runner register
```

---

## GitLab CE

**Purpose:** Full DevOps platform — Git repos, CI/CD pipelines, container registry, issue tracking.  
**Port:** `8085` (web), `2224` (SSH)  
**Data:** `service_data/gitlab/` (config, logs, data)  
**Note:** Built-in Postgres/Redis/nginx — no separate database container needed. Requires ~4GB RAM minimum.

```bash
cp gitlab/.env.example gitlab/.env
# edit .env
```

```env
DATA_ROOT=../service_data/gitlab
GITLAB_HOSTNAME=gitlab.yourdomain.com
GITLAB_EXTERNAL_URL=https://gitlab.yourdomain.com
GITLAB_SSH_PORT=2224
SIGNUP_ENABLED=false
```

```bash
sh homeserver.sh dev up gitlab
```

GitLab takes ~2–3 minutes to fully start on first launch.

**Admin account:**

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:8085` — prompted to set the `root` password on first login |
| Env var | Add `gitlab_rails['initial_root_password'] = 'yourpassword'` inside `GITLAB_OMNIBUS_CONFIG` **before first start** — ignored after GitLab has already initialised |
| CLI | `docker exec -it gitlab gitlab-rake "gitlab:password:reset[root]"` — works any time, including after first start |

**Actions runner (optional):**

```bash
sh homeserver.sh dev up gitlab --profile runner
docker exec -it gitlab-runner gitlab-runner register
```

---

## Uptime Kuma

**Purpose:** Monitor services and get alerts when something goes down.  
**Port:** `3001`  
**Data:** `service_data/uptime-kuma/`

```bash
cp uptime-kuma/.env.example uptime-kuma/.env
sh homeserver.sh dev up uptime-kuma
```

**Admin account:**

| Method | How |
| --- | --- |
| First visit ✓ | Browse to `http://<ip>:3001` — create the admin account on first launch |

---

## Dozzle

**Purpose:** Real-time Docker container log viewer in the browser.  
**Port:** `9999`  
**Access:** Read-only Docker socket mount — no `.env` needed.

```bash
sh homeserver.sh dev up dozzle
```

**Admin account:** No login by default — consider NPM access list if exposed publicly.

---

## NPM Proxy Hosts

→ See [11 — Services Reference](11-services-reference.md) for the full NPM proxy host table and per-service notes.

---

[← Firewall](09-firewall.md) | [Home](../setup.md)
