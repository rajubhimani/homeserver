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
./homeserver.sh jellyfin dev
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
./homeserver.sh vaultwarden dev
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
./homeserver.sh paperless dev
```

Admin account is created automatically from `PAPERLESS_ADMIN_USER` / `PAPERLESS_ADMIN_PASSWORD` on first start.

---

## Stirling PDF

**Purpose:** PDF toolkit — merge, split, compress, convert, OCR.  
**Port:** `8089`  
**Data:** `${DATA_ROOT}/stirling-pdf/`

```bash
cd ~/homeserver/stirling-pdf
cp .env.example .env
# set DATA_ROOT
./homeserver.sh stirling-pdf dev
```

No login required by default. All processing is local.

---

## Mealie

**Purpose:** Recipe manager and meal planner.  
**Port:** `9925`  
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
MEALIE_BASE_URL=http://192.168.1.100:9925
```

```bash
./homeserver.sh mealie dev
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
./homeserver.sh gitea dev
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
./homeserver.sh uptime-kuma dev
```

Create admin account on first visit. Add monitors for each service URL.

---

## Dozzle

**Purpose:** Real-time Docker container log viewer in the browser.  
**Port:** `9999`  
**Access:** Read-only Docker socket mount — no `.env` needed.

```bash
./homeserver.sh dozzle dev
```

Open `http://<ip>:9999` — all running containers are listed immediately. No login by default.

---

## NPM Proxy Hosts

Add these in Nginx Proxy Manager for production (Cloudflare) access:

| Domain | Forward Hostname | Forward Port |
| --- | --- | --- |
| `jellyfin.yourdomain.com` | `jellyfin` | `8096` |
| `vaultwarden.yourdomain.com` | `vaultwarden` | `80` |
| `paperless.yourdomain.com` | `paperless` | `8000` |
| `stirling-pdf.yourdomain.com` | `stirling-pdf` | `8080` |
| `mealie.yourdomain.com` | `mealie` | `9000` |
| `gitea.yourdomain.com` | `gitea` | `3000` |
| `uptime-kuma.yourdomain.com` | `uptime-kuma` | `3001` |
| `dozzle.yourdomain.com` | `dozzle` | `8080` |

> Forward hostname is the Docker **container name**. NPM resolves it via the shared `homeserver` network.

---

[← Firewall](09-firewall.md) | [Home](../setup.md)
