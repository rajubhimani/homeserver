# 08 — Maintenance

[← Landing Page](07-landing.md) | [Home](../setup.md)

---

## homeserver.sh

All services are managed via `homeserver.sh` in the repo root.

```bash
# start all services (dev by default)
./homeserver.sh

# start all — prod mode (ports on 127.0.0.1 only, nginx proxies)
./homeserver.sh all prod

# start a single service
./homeserver.sh jellyfin
./homeserver.sh jellyfin prod

# stop all
./homeserver.sh down

# stop one service
./homeserver.sh down mealie

# follow logs
./homeserver.sh logs immich
```

---

## Monthly updates

Pull latest images and recreate containers:

**All services at once:**
```bash
# dev
find ~/homeserver -maxdepth 2 -name "*compose.yml" | xargs -I{} sh -c 'docker compose -f {} pull 2>/dev/null'; ./homeserver.sh all dev

# prod
find ~/homeserver -maxdepth 2 -name "*compose.yml" | xargs -I{} sh -c 'docker compose -f {} pull 2>/dev/null'; ./homeserver.sh all prod
```

**Individual service:**
```bash
cd ~/homeserver/immich
docker compose pull && ./homeserver.sh immich dev
```

---

## Health checks

```bash
# all containers running?
docker ps

# disk usage
df -h /mnt/seagate

# container logs (any service)
docker compose logs --tail=50 <container-name>

# tunnel status (Cloudflare path only)
sudo systemctl status cloudflared
```

---

## Remote Management from Mac

Docker context lets you run all `docker` commands on the server directly from your Mac terminal.

### One-time setup

```bash
# 1. Add server host key to known_hosts
ssh-keyscan -H server-ip >> ~/.ssh/known_hosts

# 2. Copy your SSH key to the server (enter password once)
ssh-copy-id user@server-ip
```

**Step 3 — keep your key loaded (pick one):**

**Option A — macOS Keychain** (persists across reboots, macOS only):

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

Add to `~/.ssh/config` so the key is loaded automatically:

```text
Host server-ip
  UseKeychain yes
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_ed25519
```

**Option B — auto-start ssh-agent in shell profile** (works on any Unix shell):

Add to `~/.zshrc` or `~/.bashrc`:

```bash
if [ -z "$SSH_AUTH_SOCK" ]; then
  eval "$(ssh-agent -s)" > /dev/null
  ssh-add ~/.ssh/id_ed25519 2>/dev/null
fi
```

Then reload: `source ~/.zshrc`

```bash
# 4. Create and activate the Docker context
docker context create homeserver --docker "host=ssh://user@server-ip"
docker context use homeserver

# verify — should list containers on the server
docker ps
```

### Daily use

```bash
docker context ls
docker context use homeserver   # switch to server
docker context use default      # back to local
docker --context homeserver ps  # one-off without switching
```

> Context persists across terminal sessions.

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Container not starting | `./homeserver.sh <service> dev` |
| `network homeserver not found` | `docker network create homeserver` |
| Data drive not mounted | `sudo mount -a` |
| Tunnel not routing | `sudo systemctl restart cloudflared` → `journalctl -u cloudflared -f` |
| Nextcloud DB permission error | `docker compose down && rm -rf /mnt/seagate/postgres-nextcloud/* && docker compose up -d` |
| Nextcloud trusted domain error | Add domain/IP to `NEXTCLOUD_TRUSTED_DOMAINS` in `.env`, restart |
| Immich `ENOTFOUND database` | `DB_URL` must use `immich-database` as hostname, not `localhost` |
| Immich `ENOTFOUND redis` | `REDIS_HOSTNAME: immich-redis` must be in environment block |
| Mealie DB connection error | Check `POSTGRES_SERVER` (not `POSTGRES_HOST`) in compose environment |
| Landing status always green | Container responding with 502 — check if service is actually running |
| Landing nginx fails to start | `host not found in upstream` — ensure `set $upstream` is used in `nginx.conf` |
| `docker ps` from Mac fails | Run `eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519` |
| `Host key verification failed` | Run `ssh-keyscan -H server-ip >> ~/.ssh/known_hosts` |

## Common gotchas

- **Passwords in `.env`** — avoid `$`, `'`, `!`. Use alphanumeric or escape `$` as `$$`
- **Shared network** — must exist before any `docker compose up`. Re-create with `docker network create homeserver`
- **No SSL in NPM (Cloudflare path)** — Cloudflare terminates TLS. Adding certs in NPM causes double-encryption
- **Immich admin** — must be created via browser on first launch, not env vars
- **Vaultwarden signups** — disabled by default. Invite users via `/admin` panel
- **Mealie default login** — `changeme@example.com` / `MyPassword` — change immediately
- **Landing nginx config changes** — require container restart; `index.html` changes do not
- **compose.yml indentation** — use 2 or 4 spaces consistently, never tabs
- **Docker context is global** — switching affects all terminal windows

---

## Quick Reference

```bash
# create shared network (one-time)
docker network create homeserver

# start/stop all
./homeserver.sh all dev
./homeserver.sh all prod
./homeserver.sh down

# start/stop one service
./homeserver.sh jellyfin dev
./homeserver.sh down jellyfin

# follow logs
./homeserver.sh logs nextcloud
./homeserver.sh logs immich

# check env vars inside container
docker exec nextcloud env | grep POSTGRES
docker exec immich-server env | grep DB_URL

# immich with ML
cd ~/homeserver/immich && docker compose --profile ml up -d

# tunnel (Cloudflare path)
sudo systemctl status cloudflared
sudo systemctl restart cloudflared

# remote context (Mac → server)
docker context use homeserver
docker context use default
docker context ls
```

---

[← Landing Page](07-landing.md) | [Home](../setup.md)
