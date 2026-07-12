# 08 — Maintenance

[← Landing Page](07-landing.md) | [Home](../setup.md)

---

## homeserver.py

All services are managed via `homeserver.py` in the repo root.

```bash
# Tiers — MIN ⊂ CORE ⊂ ALL
uv run homeserver.py dev up min          # infrastructure only
uv run homeserver.py dev up core         # min + nextcloud
uv run homeserver.py dev up all          # everything
uv run homeserver.py dev down min
uv run homeserver.py dev down core
uv run homeserver.py dev down all        # stops every service, reverse order

# Start / stop specific services
uv run homeserver.py dev up jellyfin
uv run homeserver.py dev down mealie
uv run homeserver.py dev up landing nextcloud

# Production (ports on 127.0.0.1 only)
uv run homeserver.py prod up all

# Follow logs
uv run homeserver.py dev logs immich

# Immich with ML profile
uv run homeserver.py dev up immich --profile ml
uv run homeserver.py dev down immich --profile ml

# Update running services to latest images
uv run homeserver.py dev update running
uv run homeserver.py dev update all
uv run homeserver.py dev update jellyfin
```

> The shared `homeserver` Docker network is created automatically if missing on every `up` command.

---

## Monthly updates

Pull latest images and recreate containers:

**All services at once:**

```bash
uv run homeserver.py dev update all
uv run homeserver.py prod update all
```

**Only currently running services:**

```bash
uv run homeserver.py dev update running
```

**Individual service:**

```bash
uv run homeserver.py dev update immich
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

## Running on a resource-constrained host

If your server is a repurposed desktop/laptop (shared with other work, low core count, 8-16GB RAM) rather than a dedicated machine, `up all` can easily oversubscribe it — Postgres instances, Immich, and multi-container stacks like Plane add up fast. Check first, then apply the fixes below only where they help.

**Check current load before assuming a service is broken:**

```bash
uptime           # load average — compare against `nproc`
free -h           # used / free / swap
docker stats --no-stream   # per-container CPU/memory
```

A container reporting "unhealthy" right after a restart batch is often just the healthcheck probe itself failing to get CPU-scheduled in time under load — not a real failure. Check `docker logs <container>` for the app's own "ready" message before assuming the config is wrong.

**1. Run fewer services at once.** This is the first and biggest lever — see the `SERVICES_MIN`/`SERVICES_CORE`/`SERVICES_EXTRA` tiers in `CLAUDE.md`. Use `up core` day-to-day and bring up `SERVICES_EXTRA` services individually only when actively using them, instead of `up all`.

**2. Tune every Postgres container's own memory settings, plus a hard cap as a backstop.** A memory cap alone (`deploy.resources.limits.memory`) isn't enough — Postgres doesn't know the cap exists and will try to use its defaults, getting OOM-killed under load (migrations, vacuum, big queries). Tune the internal settings too so it paces itself:

```yaml
services:
  <service>-db:
    image: postgres:18.4
    command: postgres -c shared_buffers=128MB -c max_connections=20 -c work_mem=4MB -c maintenance_work_mem=64MB -c effective_cache_size=256MB
    deploy:
      resources:
        limits:
          memory: 384M
    # ...existing environment/volumes/healthcheck
```

Use `max_connections=20` / cap `384M` for single-consumer services (most of them). Use `max_connections=50` / cap `512M` for services with multiple concurrent DB consumers (Nextcloud, Plane, Immich — each has more than one container talking to its DB).

> **immich-db is a special case.** Its image (`ghcr.io/immich-app/postgres`) defaults to `Cmd: postgres -c config_file=/etc/postgresql/postgresql.conf` — that custom config file is required for pgvector/vectorchord's `shared_preload_libraries`. Any `command:` override on it must **keep** `-c config_file=/etc/postgresql/postgresql.conf` as the first flag and add tuning flags after it:
> ```yaml
> command: postgres -c config_file=/etc/postgresql/postgresql.conf -c shared_buffers=128MB -c max_connections=50 -c work_mem=4MB -c maintenance_work_mem=64MB -c effective_cache_size=384MB
> ```
> Before overriding `command:` on any vendor-customized Postgres image, check its real default first: `docker inspect <image> --format '{{.Config.Cmd}}'`. Overriding it blind can silently drop required flags.
>
> After changing a DB-only `command:`/`deploy:` block, you only need to recreate that one container — this is much faster than a full service restart, which would otherwise wait on every dependent container's healthcheck:
> ```bash
> cd <service>/
> DATA_ROOT="../service_data/<service>" DOMAIN="yourdomain.com" docker compose -f compose.yml -f compose.prod.yml up -d --no-deps <service>-db
> ```
>
> Verify the tuning actually applied (don't just trust `docker ps`):
> ```bash
> docker exec <service>-db psql -U <postgres-user> -c "SHOW max_connections; SHOW shared_buffers;"
> ```

**3. Throttle Immich's job concurrency — via the Admin UI, not env vars.** `IMMICH_CONCURRENCY_*` environment variables do not exist in Immich and are silently ignored if set — this is a live database setting, not a compose/env change:

1. Log into Immich as an admin.
2. Go to **Administration → Settings → Job Settings**.
3. You'll see a concurrency slider/number for each job type: Thumbnail Generation, Metadata Extraction, Video Conversion, Face Detection, Smart Search, etc.
4. Set the ones you want throttled (Thumbnail Generation, Metadata Extraction, Video Conversion) down to `1` on a low-core-count host — don't exceed your CPU core count for any of them.
5. Save — takes effect immediately for new jobs, no restart needed.

**4. If your swap is zram (common on modern Fedora/desktop setups), raise `vm.swappiness` instead of lowering it.** Check with `zramctl` and `swapon --show` — if your swap device is `/dev/zram0`, it's compressed RAM, not slow disk. The usual advice to keep swappiness low (Fedora's default is often already conservative, e.g. `10`) is aimed at disk-backed swap. For zram, a higher value (100-180) makes the kernel offload cold pages to it earlier, freeing real RAM sooner instead of waiting until the system is already under pressure:
```bash
cat /proc/sys/vm/swappiness   # check current value
sudo sysctl vm.swappiness=150 # raise for zram (temporary — add to /etc/sysctl.d/ to persist)
```

---

## Troubleshooting

Reactive fixes, keyed by symptom:

| Problem | Fix |
| --- | --- |
| Container not starting | `uv run homeserver.py dev up <service>` then check `uv run homeserver.py dev logs <service>` |
| `network homeserver not found` | `homeserver.py` auto-creates it — or run `docker network create homeserver` manually |
| Data drive not mounted | `sudo mount -a` |
| Tunnel not routing | `sudo systemctl restart cloudflared` → `journalctl -u cloudflared -f` |
| Nextcloud/Postgres data directory ownership or corruption error | **Do not delete the data to "fix" this** — Postgres/MariaDB/RabbitMQ data lives in a named Docker volume (not a bind mount), so this class of error shouldn't occur under normal operation. If it does, first `uv run homeserver.py dev restore <service>` from the last snapshot rather than resetting; see the `homeserver-postgres` skill for why bind-mounting DB data is unsafe and never worth reintroducing |
| Nextcloud trusted domain error | Should self-heal on next restart — `nextcloud/hooks/before-starting/02-configure-proxy.sh` sets `trusted_domains`/`trusted_proxies` via `occ` automatically on every startup. If it persists, check the hook actually ran: `docker exec nextcloud php occ config:system:get trusted_domains`; see [`docs/services/nextcloud.md`](services/nextcloud.md) |
| Immich `ENOTFOUND database` | `DB_URL` must use `immich-database` as hostname, not `localhost` |
| Immich `ENOTFOUND redis` | `REDIS_HOSTNAME: immich-redis` must be in environment block |
| Mealie DB connection error | Check `POSTGRES_SERVER` (not `POSTGRES_HOST`) in compose environment |
| Landing status always green | Container responding with 502 — check if service is actually running |
| Landing nginx fails to start | `host not found in upstream` — ensure `set $upstream` is used in `nginx.conf` |
| `docker ps` from Mac fails | Run `eval "$(ssh-agent -s)" && ssh-add ~/.ssh/id_ed25519` |
| `Host key verification failed` | Run `ssh-keyscan -H server-ip >> ~/.ssh/known_hosts` |

## Common gotchas

Preventive knowledge — things to know *before* they bite you, as opposed to the reactive fixes above:

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
