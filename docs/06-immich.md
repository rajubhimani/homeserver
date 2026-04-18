# 06 — Immich

[← Nextcloud](05-nextcloud.md) | [Home](../setup.md) | [Next: Landing Page →](07-landing.md)

---

## Create .env

```bash
mkdir -p ~/homeserver/immich
cd ~/homeserver/immich
```

```env
UPLOAD_LOCATION=/mnt/seagate/immich
DB_DATA_LOCATION=/mnt/seagate/postgres-immich

# Generate with: openssl rand -hex 32
IMMICH_SECRET=your_hex_secret_here

# Postgres
DB_PASSWORD=your_strong_password
DB_USERNAME=immich
DB_DATABASE_NAME=immich
DB_URL=postgresql://immich:your_strong_password@immich-database:5432/immich
```

> ⚠️ `DB_URL` must use `immich-database` as the hostname — not `localhost`.

---

## Start

**Production (Cloudflare)** — no ports exposed, NPM routes via Docker network:
```bash
cd ~/homeserver/immich
docker compose up -d
docker compose logs -f immich-server
```

**Testing (Tailscale)** — exposes port 2283 via dev override:
```bash
cd ~/homeserver/immich
docker compose -f compose.yml -f compose.dev.yml up -d
docker compose logs -f immich-server
```

**Cloudflare path:** open `https://immich.yourdomain.com`  
**Tailscale path:** open `http://100.x.x.x:2283`

> ⚠️ Immich does not support creating the admin account via env vars — use the browser on first launch.

---

## Machine Learning (optional)

ML enables facial recognition and smart search. Disabled by default via `profiles: [ml]` to save RAM.

**Disable in UI** (recommended for low-resource setups):

```text
Admin → Administration → Machine Learning → toggle off → Save
```

**Enable ML:**

```bash
docker compose --profile ml up -d
```

Then in UI: `Admin → Machine Learning → toggle on → Save`

Run initial jobs under `Admin → Jobs`: Smart Search → Run All, Face Detection → Run All.

---

## Mobile App Setup

Install the **Immich** app (Android / iOS — free).

### Server URL by access path

**Cloudflare path:**
```text
https://immich.yourdomain.com
```

**Tailscale path:**
```text
http://100.x.x.x:2283
```

> Tailscale backup only runs when the device is connected to the tailnet. Cloudflare path works anywhere.

Login with the user's account, then enable auto-backup in app settings.

---

[← Nextcloud](05-nextcloud.md) | [Home](../setup.md) | [Next: Landing Page →](07-landing.md)
