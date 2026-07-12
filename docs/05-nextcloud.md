# 05 — Nextcloud

[← Reverse Proxy](04-nginx.md) | [Home](../setup.md) | [Next: Immich →](06-immich.md)

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
```

> ⚠️ Avoid `$`, `'`, `!` in passwords — they cause `.env` parsing issues. Use alphanumeric or escape `$` as `$$`.

**Trusted domains/proxies and HTTPS detection are configured automatically** — `nextcloud/hooks/before-starting/02-configure-proxy.sh` sets `trusted_domains` (`localhost`, `nextcloud.${DOMAIN}`, `*.${DOMAIN}`), `trusted_proxies`, and `overwriteprotocol=https` via `occ` on every startup, so there's nothing to set in `.env` for the Cloudflare path. **Tailscale IP-only access** (no domain) isn't covered by that wildcard — if you need it, add a `trusted_domains` line for your Tailscale IP/hostname directly in that script. See [`docs/services/nextcloud.md`](services/nextcloud.md) if this ever needs troubleshooting.

---

## Start

```bash
uv run homeserver.py dev up nextcloud
uv run homeserver.py dev logs nextcloud
# ready when you see: Apache configured
```

For prod (ports on localhost only):

```bash
uv run homeserver.py prod up nextcloud
```

**Cloudflare path:** open `https://nextcloud.yourdomain.com`  
**Tailscale path:** open `http://100.x.x.x:8081`

Login with your admin credentials.

---

## Volume Notes

Nextcloud uses **partial volume mounts** (not the full `/var/www/html`) — `html`, `config`, `data`, and `custom_apps` are each their own **named Docker volume** (`nextcloud-html`, `nextcloud-config`, `nextcloud-data`, `nextcloud-custom-apps`; see `nextcloud/compose.yml`), not host bind mounts. A `before-starting` hook (`nextcloud/hooks/before-starting/00-sync-php.sh`) runs rsync on every startup to populate the PHP files from the image into the container.

> **Why not mount the full `/var/www/html`?** Docker's seccomp profile blocks `lchown` on symlinks. Nextcloud's rsync tries to chown `.map.license` symlinks, fails, and crash-loops. Partial mounts avoid this entirely.

See [`docs/services/nextcloud.md`](services/nextcloud.md) for why these are named volumes rather than bind mounts, and how to migrate existing data into them.

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

[← Reverse Proxy](04-nginx.md) | [Home](../setup.md) | [Next: Immich →](06-immich.md)
