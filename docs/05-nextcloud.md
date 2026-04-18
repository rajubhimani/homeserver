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
