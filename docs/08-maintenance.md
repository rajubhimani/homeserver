# 08 — Maintenance

[← Landing Page](07-landing.md) | [Home](../setup.md)

---

## homeserver.sh

All services are managed via `homeserver.sh` in the repo root.

```bash
# Tiers — MIN ⊂ CORE ⊂ ALL
sh homeserver.sh dev up min          # infrastructure only
sh homeserver.sh dev up core         # min + nextcloud
sh homeserver.sh dev up all          # everything
sh homeserver.sh dev down min
sh homeserver.sh dev down core
sh homeserver.sh dev down all        # stops every service, reverse order

# Start / stop specific services
sh homeserver.sh dev up jellyfin
sh homeserver.sh dev down mealie
sh homeserver.sh dev up landing nextcloud

# Production (ports on 127.0.0.1 only)
sh homeserver.sh prod up all

# Follow logs
sh homeserver.sh dev logs immich

# Immich with ML profile
sh homeserver.sh dev up immich --profile ml
sh homeserver.sh dev down immich --profile ml

# Update running services to latest images
sh homeserver.sh dev update running
sh homeserver.sh dev update all
sh homeserver.sh dev update jellyfin
```

> The shared `homeserver` Docker network is created automatically if missing on every `up` command.

---

## Monthly updates

Pull latest images and recreate containers:

**All services at once:**

```bash
sh homeserver.sh dev update all
sh homeserver.sh prod update all
```

**Only currently running services:**

```bash
sh homeserver.sh dev update running
```

**Individual service:**

```bash
sh homeserver.sh dev update immich
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
| Container not starting | `sh homeserver.sh dev up <service>` then check `sh homeserver.sh dev logs <service>` |
| `network homeserver not found` | `homeserver.sh` auto-creates it — or run `docker network create homeserver` manually |
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
- **No SSL in the reverse proxy (Cloudflare path)** — Cloudflare terminates TLS. Adding certs causes double-encryption
- **Immich admin** — must be created via browser on first launch, not env vars
- **Vaultwarden signups** — disabled by default. Invite users via `/admin` panel
- **Mealie default login** — `changeme@example.com` / `MyPassword` — change immediately
- **Landing nginx config changes** — require container restart; `index.html` changes do not
- **compose.yml indentation** — use 2 or 4 spaces consistently, never tabs
- **Docker context is global** — switching affects all terminal windows

---

[← Landing Page](07-landing.md) | [Home](../setup.md)
