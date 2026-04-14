# Self-Hosted Personal Cloud — Docker Setup Guide

> Nextcloud + Immich on any Linux machine  
> Replaces Google Drive + Google Photos  
> Family-ready with individual logins

---

## Stack

| Service | Purpose | Replaces |
|---|---|---|
| Nextcloud | File storage + sharing | Google Drive |
| Immich | Photo management | Google Photos |
| Tailscale | Remote access | VPN / port forwarding |
| Docker | Container runtime | Manual installs |

---

## Requirements

- Any x86-64 machine (laptop, mini PC, old desktop)
- Minimum 4GB RAM (8GB+ recommended)
- One drive for OS + Docker (SSD preferred)
- One drive for data (internal or USB, formatted ext4)
- Ubuntu 24.04 LTS (or any Debian-based distro)

---

## Folder Structure

```
~/homeserver/
├── nextcloud/
│   ├── compose.yml
│   └── .env
└── immich/
    ├── compose.yml
    └── .env
```

Data lives on your data drive (e.g. `/mnt/seagate`):

```
/mnt/seagate/
├── nextcloud/
├── immich/
├── postgres-nextcloud/
└── postgres-immich/
```

---

## Phase 1 — Prepare Data Drive

Format your data drive to ext4 (skip if already done):

```bash
# identify drive
lsblk

# format with label (destructive — back up first)
sudo mkfs.ext4 -L "seagate" /dev/sdX

# create mount point
sudo mkdir -p /mnt/seagate

# get UUID
sudo blkid | grep seagate
```

Add to `/etc/fstab` for persistent mount:

```bash
sudo nano /etc/fstab

# add this line (replace UUID with yours)
UUID=your-uuid-here  /mnt/seagate  ext4  defaults,nofail,x-systemd.device-timeout=10  0  2
```

Apply and verify:

```bash
sudo mount -a
ls /mnt/seagate
```

Create folder structure:

```bash
sudo mkdir -p /mnt/seagate/{nextcloud,immich,postgres-nextcloud,postgres-immich}
sudo chown -R $USER:$USER /mnt/seagate
```

---

## Phase 2 — Install Docker

```bash
# install
curl -fsSL https://get.docker.com | sudo sh

# add user to docker group
sudo usermod -aG docker $USER

# log out and back in, then verify
docker --version
docker compose version

# enable on boot
sudo systemctl enable docker
```

---

## Phase 3 — Nextcloud

### Create files

```bash
mkdir -p ~/homeserver/nextcloud
cd ~/homeserver/nextcloud
```

**`.env`**

```env
# On Mac for testing use ./data, on Ubuntu use /mnt/seagate
DATA_ROOT=/mnt/seagate

# Postgres
POSTGRES_DB=nextcloud
POSTGRES_USER=nextcloud
POSTGRES_PASSWORD=your_strong_password

# Nextcloud admin
NEXTCLOUD_ADMIN_USER=admin
NEXTCLOUD_ADMIN_PASSWORD=your_strong_password

# Add your server IP and Tailscale domain
NEXTCLOUD_TRUSTED_DOMAINS=localhost 192.168.1.100 *.ts.net
```

> ⚠️ Avoid `$`, `'`, `!` in passwords — they cause `.env` parsing issues. Use long alphanumeric passwords or escape `$` as `$$`.

**`compose.yml`**

```yaml
services:
  nextcloud-db:
    image: postgres:16
    container_name: nextcloud-db
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ${DATA_ROOT}/postgres-nextcloud:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  nextcloud:
    image: nextcloud:latest
    container_name: nextcloud
    restart: unless-stopped
    ports:
      - "8080:80"
    env_file: .env
    environment:
      POSTGRES_HOST: nextcloud-db
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      NEXTCLOUD_ADMIN_USER: ${NEXTCLOUD_ADMIN_USER}
      NEXTCLOUD_ADMIN_PASSWORD: ${NEXTCLOUD_ADMIN_PASSWORD}
      NEXTCLOUD_TRUSTED_DOMAINS: ${NEXTCLOUD_TRUSTED_DOMAINS}
    volumes:
      - ${DATA_ROOT}/nextcloud:/var/www/html/data
      - ${DATA_ROOT}:/mnt/seagate
    depends_on:
      nextcloud-db:
        condition: service_healthy
```

### Start

```bash
docker compose up -d
docker compose logs -f nextcloud
# ready when you see: Apache configured
```

Open `http://localhost:8080` — login with admin credentials.

### Enable External Storage

```
Apps → search "External storage support" → Enable

Settings → Administration → External Storage
→ Add Storage
  Folder name: Seagate
  Storage type: Local
  Configuration: /mnt/seagate
  Available for: All users
→ click checkmark (green = working)
```

### Create Family Accounts

```
Top right avatar → Administration → Users → New User
```

One account per family member.

---

## Phase 4 — Immich

### Create files

```bash
mkdir -p ~/homeserver/immich
cd ~/homeserver/immich
```

**`.env`**

```env
# On Mac for testing use relative paths, on Ubuntu use /mnt/seagate paths
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

> ⚠️ `DB_URL` must use the service name `immich-database` as hostname — not `localhost`.

**`compose.yml`**

```yaml
services:
  immich-server:
    image: ghcr.io/immich-app/immich-server:release
    container_name: immich-server
    restart: unless-stopped
    ports:
      - "2283:2283"
    env_file: .env
    environment:
      DB_URL: ${DB_URL}
      DB_PASSWORD: ${DB_PASSWORD}
      DB_USERNAME: ${DB_USERNAME}
      DB_DATABASE_NAME: ${DB_DATABASE_NAME}
      IMMICH_SECRET: ${IMMICH_SECRET}
      REDIS_HOSTNAME: immich-redis
    volumes:
      - ${UPLOAD_LOCATION}:/usr/src/app/upload
      - /etc/localtime:/etc/localtime:ro
    depends_on:
      immich-database:
        condition: service_healthy
      immich-redis:
        condition: service_healthy

  immich-machine-learning:
    image: ghcr.io/immich-app/immich-machine-learning:release
    container_name: immich-ml
    restart: unless-stopped
    env_file: .env
    profiles:
      - ml
    volumes:
      - immich-model-cache:/cache

  immich-redis:
    image: redis:7-alpine
    container_name: immich-redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  immich-database:
    image: ghcr.io/immich-app/postgres:16-vectorchord0.5.3-pgvector0.8.1
    container_name: immich-db
    restart: unless-stopped
    env_file: .env
    environment:
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_USER: ${DB_USERNAME}
      POSTGRES_DB: ${DB_DATABASE_NAME}
    volumes:
      - ${DB_DATA_LOCATION}:/var/lib/postgresql/data
    shm_size: 128mb
    healthcheck:
      test: >-
        pg_isready --dbname="$${POSTGRES_DB}" --username="$${POSTGRES_USER}" || exit 1
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

volumes:
  immich-model-cache:
```

### Start

```bash
docker compose up -d
docker compose logs -f immich-server
```

Open `http://localhost:2283` — first launch shows admin account creation screen.

> ⚠️ Immich does not support creating admin via env vars — you must use the browser on first launch.

### Machine Learning (optional)

ML is disabled by default via `profiles: [ml]`. This saves RAM on low-power hardware.

**Disable ML in UI** (do this after first login):

```
Admin → Administration → Machine Learning → toggle off → Save
```

**Enable ML in future:**

```bash
# start ML container
docker compose --profile ml up -d

# then enable in UI
Admin → Machine Learning → toggle on → Save

# process existing library
Admin → Jobs → Smart Search → Run All
Admin → Jobs → Face Detection → Run All
```

### Family Mobile Setup

- Install **Immich** app (Android / iOS — free)
- Server URL: `http://<tailscale-ip>:2283`
- Login with their account
- Enable auto-backup in app settings

---

## Phase 5 — Tailscale

```bash
# install
curl -fsSL https://tailscale.com/install.sh | sh

# authenticate
sudo tailscale up
# visit the URL it gives you to authorize

# get your Tailscale IP
tailscale ip -4
```

Family access URLs (replace with your actual Tailscale IP):

| Service | URL |
|---|---|
| Nextcloud | `http://100.x.x.x:8080` |
| Immich | `http://100.x.x.x:2283` |
| SSH | `ssh user@100.x.x.x` |

Each family member installs Tailscale on their device and joins your tailnet.

---

## Mac → Ubuntu Deployment

### Develop on Mac, deploy to Ubuntu

Use `./data` paths in `.env` for Mac testing, swap to `/mnt/seagate` paths for Ubuntu.

**Push configs to server:**

```bash
rsync -avz \
  --exclude='data/' \
  ~/homeserver/ \
  user@server-ip:~/docker/
```

**SSH in and update .env files:**

```bash
ssh user@server-ip

# nextcloud
cd ~/docker/nextcloud
sed -i 's|DATA_ROOT=.*|DATA_ROOT=/mnt/seagate|' .env

# immich
cd ~/docker/immich
sed -i 's|UPLOAD_LOCATION=.*|UPLOAD_LOCATION=/mnt/seagate/immich|' .env
sed -i 's|DB_DATA_LOCATION=.*|DB_DATA_LOCATION=/mnt/seagate/postgres-immich|' .env
```

**Start everything:**

```bash
cd ~/docker/nextcloud && docker compose up -d
cd ~/docker/immich && docker compose up -d
```

**Remote management via Docker context (from Mac):**

```bash
# one-time setup
docker context create homeserver \
  --docker "host=ssh://user@server-ip"

# switch to it
docker context use homeserver

# now all docker commands run on server
docker ps
docker compose logs -f immich-server
```

---

## Maintenance

### Monthly updates

```bash
cd ~/homeserver/nextcloud && docker compose pull && docker compose up -d
cd ~/homeserver/immich && docker compose pull && docker compose up -d
```

### Health checks

```bash
# all containers running?
docker ps

# disk usage
df -h /mnt/seagate

# container logs
docker compose logs --tail=50 nextcloud
docker compose logs --tail=50 immich-server
```

### Troubleshooting

| Problem | Fix |
|---|---|
| Container not starting | `docker compose up -d` in that app's folder |
| Seagate not mounted | `sudo mount -a` |
| Tailscale disconnected | `sudo tailscale up` |
| Nextcloud DB permission error | `docker compose down && rm -rf data/postgres-nextcloud/* && docker compose up -d` |
| Immich `ENOTFOUND database` | Check `DB_URL` is in `environment:` block in compose.yml, not just `.env` |
| Immich `ENOTFOUND redis` | Add `REDIS_HOSTNAME: immich-redis` to environment block |

### Common gotchas

- **Passwords in `.env`** — avoid `$`, `'`, `!` characters. Use alphanumeric or escape `$` as `$$`
- **DB_URL hostname** — must match the service name in compose (`immich-database`), never `localhost`
- **Nextcloud permission error** — caused by partial init. Wipe postgres data folder and restart clean
- **Immich admin** — cannot be created via env vars, must use browser on first launch
- **USB drives for ZFS** — don't put USB drives in ZFS pools, use ext4 + fstab mount instead
- **compose.yml indentation** — YAML is indentation-sensitive, use 2 or 4 spaces consistently, never tabs

---

## Quick Reference

```bash
# start all services
cd ~/homeserver/nextcloud && docker compose up -d
cd ~/homeserver/immich && docker compose up -d

# stop all services
cd ~/homeserver/nextcloud && docker compose down
cd ~/homeserver/immich && docker compose down

# restart a single container
docker restart nextcloud
docker restart immich-server

# view logs
docker compose logs -f nextcloud
docker compose logs -f immich-server

# check env vars inside container
docker exec nextcloud env | grep POSTGRES
docker exec immich-server env | grep DB_URL

# start immich with ML enabled
cd ~/homeserver/immich && docker compose --profile ml up -d
```
