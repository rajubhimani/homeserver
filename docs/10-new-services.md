# 10 — New Services

[← Firewall](09-firewall.md) | [Home](../setup.md)

---

All new services follow the same pattern as Nextcloud and Immich:

- `compose.yml` — base config, no ports
- `compose.dev.yml` — ports on all interfaces (direct access)
- `compose.prod.yml` — ports on `127.0.0.1` only (nginx proxy handles external)
- `.env` — secrets and paths (copy from `.env.example`)

Use `homeserver.sh` to manage them (see [Maintenance](08-maintenance.md)).

---

## Jellyfin

**Purpose:** Stream movies, TV shows, and music from your server.  
**Port:** `8096`  
**Data:** `${DATA_ROOT}/jellyfin/`

```bash
cd ~/homeserver/jellyfin
cp .env.example .env
# edit .env — set DATA_ROOT and MEDIA_ROOT
```

```env
DATA_ROOT=/mnt/seagate
MEDIA_ROOT=/mnt/seagate/media
```

```bash
sh homeserver.sh dev up jellyfin
```

Open `http://<ip>:8096` — complete the setup wizard on first launch.

---

## Vaultwarden

**Purpose:** Self-hosted password manager, compatible with all Bitwarden apps.  
**Port:** `8200`  
**Data:** `${DATA_ROOT}/vaultwarden/`

```bash
cd ~/homeserver/vaultwarden
cp .env.example .env
# edit .env
```

```env
DATA_ROOT=/mnt/seagate
VAULTWARDEN_DOMAIN=https://vaultwarden.yourdomain.com
ADMIN_TOKEN=<openssl rand -base64 48>
```

```bash
sh homeserver.sh dev up vaultwarden
```

**Onboarding users (no SMTP needed):**
1. Go to `http://<ip>:8200/admin` → enter `ADMIN_TOKEN`
2. Users → Invite User → enter their email
3. Share `http://<ip>:8200/#/signup` with them
4. They register using the invited email and set their master password

> ⚠️ `SIGNUPS_ALLOWED` is `false` by default — use admin panel to invite.

---

## Paperless-ngx

**Purpose:** Scan, OCR, and archive documents. Full-text search.  
**Port:** `8010`  
**Data:** `${DATA_ROOT}/paperless/`  
**Depends on:** Postgres + Redis (included in compose)

```bash
cd ~/homeserver/paperless
cp .env.example .env
# edit .env
```

```env
DATA_ROOT=/mnt/seagate
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

Admin account is created automatically from `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` on first start.

---

## Stirling PDF Lite

**Purpose:** Lightweight PDF toolkit — always on, default endpoint.  
**Port:** `8090`  
**Image:** `stirlingtools/stirling-pdf:latest-ultra-lite` (~200MB)  
**Data:** `${DATA_ROOT}/stirling-pdf-lite/`

```bash
cd ~/homeserver/stirling-pdf-lite
cp .env.example .env
# edit .env — set password
```

```env
DATA_ROOT=../data
STIRLING_ADMIN_USER=admin
STIRLING_ADMIN_PASSWORD=your_strong_password
```

```bash
sh homeserver.sh dev up stirling-pdf-lite
```

Authentication is handled via **NPM Access List** (not app-level login):
1. NPM → Access Lists → Add → set username/password + `Allow 0.0.0.0/0`
2. NPM → Proxy Hosts → `stirling-pdf-lite.yourdomain.com` → Access List → select it

> The ultra-lite image does not include built-in auth. NPM access list is the recommended approach.

---

## Stirling PDF (Full)

**Purpose:** Full PDF toolkit with OCR, LibreOffice conversion — manual start only (heavy).  
**Port:** `8089`  
**Image:** `stirlingtools/stirling-pdf:latest` (~1.5GB)  
**Data:** `${DATA_ROOT}/stirling-pdf/`

> Not in `all` — start manually when needed, stop when done.

```bash
sh homeserver.sh dev up stirling-pdf
sh homeserver.sh dev down stirling-pdf
```

```bash
cd ~/homeserver/stirling-pdf
cp .env.example .env
# set DATA_ROOT
```

No login required by default. All processing is local.

---

## Mealie

**Purpose:** Recipe manager and meal planner.  
**Port:** `9000`  
**Data:** `${DATA_ROOT}/mealie/`  
**Depends on:** Postgres (included in compose)

```bash
cd ~/homeserver/mealie
cp .env.example .env
# edit .env
```

```env
DATA_ROOT=/mnt/seagate
POSTGRES_DB=mealie
POSTGRES_USER=mealie
POSTGRES_PASSWORD=your_strong_password
MEALIE_BASE_URL=http://192.168.1.100:9000
```

```bash
sh homeserver.sh dev up mealie
```

Default login: `changeme@example.com` / `MyPassword` — change immediately after first login.

---

## Gitea

**Purpose:** Self-hosted Git service. Manage repos, issues, pull requests.  
**Port:** `3000` (web), `2222` (SSH)  
**Data:** `${DATA_ROOT}/gitea/`  
**Depends on:** Postgres (included in compose)

```bash
cd ~/homeserver/gitea
cp .env.example .env
# edit .env
```

```env
DATA_ROOT=/mnt/seagate
POSTGRES_DB=gitea
POSTGRES_USER=gitea
POSTGRES_PASSWORD=your_strong_password
GITEA_DOMAIN=gitea.yourdomain.com
GITEA_ROOT_URL=https://gitea.yourdomain.com
```

```bash
sh homeserver.sh dev up gitea
```

Complete the setup wizard on first visit. Create admin account via the web installer.

---

## Uptime Kuma

**Purpose:** Monitor services and get alerts when something goes down.  
**Port:** `3001`  
**Data:** `${DATA_ROOT}/uptime-kuma/`

```bash
cd ~/homeserver/uptime-kuma
cp .env.example .env
# set DATA_ROOT
sh homeserver.sh dev up uptime-kuma
```

Create admin account on first visit. Add monitors for each service URL.

---

## Dozzle

**Purpose:** Real-time Docker container log viewer in the browser.  
**Port:** `9999`  
**Access:** Read-only Docker socket mount — no `.env` needed.

```bash
sh homeserver.sh dev up dozzle
```

Open `http://<ip>:9999` — all running containers are listed immediately. No login by default.

---

## NPM Proxy Hosts

→ See [11 — Services Reference](11-services-reference.md) for the full NPM proxy host table and per-service notes.

---

[← Firewall](09-firewall.md) | [Home](../setup.md)
