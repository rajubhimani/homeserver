# 05 — Nextcloud

[← Nginx Proxy Manager](04-nginx.md) | [Home](../setup.md) | [Next: Immich →](06-immich.md)

---

## Create .env

```bash
mkdir -p ~/homeserver/nextcloud
cd ~/homeserver/nextcloud
```

```env
DATA_ROOT=/mnt/seagate
USER_DATA_ROOT=/mnt/seagate

# Postgres
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=your_strong_password

# Nextcloud admin
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=your_strong_password

# Trusted domains — see your access path below
NEXTCLOUD_TRUSTED_DOMAINS=
```

> ⚠️ Avoid `$`, `'`, `!` in passwords — they cause `.env` parsing issues. Use alphanumeric or escape `$` as `$$`.

### Trusted domains by access path

**Cloudflare path:**

```env
NEXTCLOUD_TRUSTED_DOMAINS=localhost nextcloud.yourdomain.com
```

**Tailscale path:**

```env
NEXTCLOUD_TRUSTED_DOMAINS=localhost 192.168.1.100 100.x.x.x
```

> `NEXTCLOUD_TRUSTED_PROXIES: nginx-proxy-manager` is already set in `compose.yml` — required for correct client IP forwarding through NPM.

---

## Start

**Production (Cloudflare)** — no ports exposed, NPM routes via Docker network:

```bash
cd ~/homeserver/nextcloud
docker compose up -d
docker compose logs -f nextcloud
# ready when you see: Apache configured
```

**Testing (Tailscale)** — exposes port 8081 via dev override:

```bash
cd ~/homeserver/nextcloud
docker compose -f compose.yml -f compose.dev.yml up -d
docker compose logs -f nextcloud
```

**Cloudflare path:** open `https://nextcloud.yourdomain.com`  
**Tailscale path:** open `http://100.x.x.x:8081`

Login with your admin credentials.

---

## Volume Notes

Nextcloud uses **partial volume mounts** (not the full `/var/www/html`):

| Host path | Container path | Purpose |
| --- | --- | --- |
| `data/nextcloud/config` | `/var/www/html/config` | Config including `config.php` |
| `data/nextcloud/data` | `/var/www/html/data` | User files |
| `data/nextcloud/custom_apps` | `/var/www/html/custom_apps` | User-installed apps |
| `data/nextcloud/version.php` | `/var/www/html/version.php` | Prevents false "new instance" detection on restart |

A `before-starting` hook (`nextcloud/hooks/before-starting/00-sync-php.sh`) runs rsync on every startup to populate the PHP files from the image into the container.

> **Why not mount the full `/var/www/html`?** Docker's seccomp profile blocks `lchown` on symlinks. Nextcloud's rsync tries to chown `.map.license` symlinks, fails, and crash-loops. Partial mounts avoid this entirely.

---

## Enable External Storage

```text
Apps → search "External storage support" → Enable

Settings → Administration → External Storage → Add Storage
  Folder name: Seagate
  Storage type: Local
  Configuration: /mnt/seagate
  Available for: All users
→ click checkmark (green = working)
```

## Create Family Accounts

```text
Top right avatar → Administration → Users → New User
```

One account per family member. They log in via the same URL you use.

---

[← Nginx Proxy Manager](04-nginx.md) | [Home](../setup.md) | [Next: Immich →](06-immich.md)
