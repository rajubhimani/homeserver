# 08 — Maintenance

[← Landing Page](07-landing.md) | [Home](../setup.md) | [Next: Firewall →](09-firewall.md)

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

# Immich — ML container starts by default now; --no-ml excludes it
# (e.g. low-resource machines that don't want face/object detection)
uv run homeserver.py dev up immich --no-ml

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

**1. Run fewer services at once.** This is the first and biggest lever — see the `SERVICES_MIN`/`SERVICES_CORE`/`SERVICES_DAILY`/`SERVICES_EXTRA` tiers in `CLAUDE.md`. Use `up core` day-to-day and bring up `SERVICES_DAILY`/`SERVICES_EXTRA` services individually only when actively using them, instead of `up all`.

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
>
> ```yaml
> command: postgres -c config_file=/etc/postgresql/postgresql.conf -c shared_buffers=128MB -c max_connections=50 -c work_mem=4MB -c maintenance_work_mem=64MB -c effective_cache_size=384MB
> ```
>
> Before overriding `command:` on any vendor-customized Postgres image, check its real default first: `docker inspect <image> --format '{{.Config.Cmd}}'`. Overriding it blind can silently drop required flags.
>
> After changing a DB-only `command:`/`deploy:` block, you only need to recreate that one container — this is much faster than a full service restart, which would otherwise wait on every dependent container's healthcheck:
>
> ```bash
> cd <service>/
> DATA_ROOT="../service_data/<service>" DOMAIN="yourdomain.com" docker compose -f compose.yml -f compose.prod.yml up -d --no-deps <service>-db
> ```
>
> Verify the tuning actually applied (don't just trust `docker ps`):
>
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

## Capping Docker's total resource usage (Fedora / native Linux)

Applies to whichever machine actually runs `dockerd` — the numbers below
(8 cores, 10GB memory, 50GB disk) were sized for a specific box (16 cores,
30GB RAM, root filesystem is btrfs) — adjust to your own `nproc`/`free -h`
before applying elsewhere. This is a host-level Docker daemon config, not
a per-service `compose.yml` change — nothing here needs a matching
`.env.example`/`docs/services/<service>.md` update, it applies uniformly
to every container on the host. The CLI's own `~/.docker/config.json`
(auth, credential helpers, plugins) is unrelated and has no resource
knobs at all — everything below is daemon-side.

**`docker/` at the repo root runs all of this for you**, parameterized by
`docker/.env` instead of hand-editing the commands below — also handles
Ubuntu (ext4 loopback image instead of a btrfs qgroup) and Windows
(Docker Desktop's own settings file) with the same three commands. See
[`docker/README.md`](../docker/README.md). The manual steps below are
still worth knowing — they're exactly what that script runs, useful for
understanding/debugging rather than typing by hand every time.

**Requires root** (`sudo`) to install — these commands need to be run
manually from a real terminal (a coding assistant without an interactive
sudo prompt can prepare the file contents but can't write to `/etc`
itself).

### Memory + CPU: a systemd slice, not a `docker.service` drop-in

The obvious-looking approach — a `systemd` drop-in on `docker.service`
itself with `MemoryMax=`/`CPUQuota=` — **does not cap container
workloads**, only the `dockerd` management process's own cgroup. With the
`systemd` cgroup driver (`docker info` → `Cgroup Driver: systemd`, true by
default on Fedora), each container's cgroup is created as a **sibling** of
`docker.service` (`system.slice/docker-<id>.scope`), not nested inside it —
so a `docker.service` drop-in silently caps almost nothing.

The correct mechanism: define a systemd **slice** with the real limits,
then tell the daemon to place every container's cgroup under that slice
via `cgroup-parent`.

```bash
sudo tee /etc/systemd/system/docker-workloads.slice <<'EOF'
[Unit]
Description=Resource limit for all Docker containers

[Slice]
# Hard ceiling — cgroup v2 OOM-kills something inside this slice if
# exceeded, never the rest of the host.
MemoryMax=10G
# Soft ceiling, set just under MemoryMax — cgroup v2 starts reclaiming/
# throttling here instead of waiting for the hard kill at MemoryMax,
# smoother degradation under pressure.
MemoryHigh=9G
# 800% = 8 of this host's 16 cores (systemd expresses CPU quota as a
# percentage of one core, so N cores = N*100%).
CPUQuota=800%
EOF

sudo tee /etc/docker/daemon.json <<'EOF'
{
  "cgroup-parent": "docker-workloads.slice",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF

sudo systemctl daemon-reload
sudo systemctl restart docker   # interrupts every currently-running container
```

`log-opts` above is a second, independent fix — unbounded container
stdout/stderr is one of the most common silent disk-fillers (same root
cause as the WSL2 VHDX incident below, different mechanism: log growth
instead of image/layer growth). `max-size: 10m` / `max-file: 3` caps each
container's logs at 30MB total, rotated.

Verify after restarting:

```bash
systemctl status docker-workloads.slice     # confirm the slice exists and is active
docker info | grep -i cgroup
systemd-cgtop                               # live view — containers should show under docker-workloads.slice
```

### Disk: btrfs quota on `/var/lib/docker`, not a Docker storage-opt

Docker's own `storage-opts: ["overlay2.size=50G"]` needs the backing
filesystem to support project quotas — XFS (`pquota` mount option) mainly.
It does **not** work on btrfs, which is this host's root filesystem
(`docker info` → `Storage Driver: overlayfs` on top of btrfs) — the option
would be silently ignored or error, not enforced. The real mechanism on
btrfs is a **qgroup limit**, but qgroups apply per-**subvolume**, and
`/var/lib/docker` is very likely just a plain directory inside the root
subvolume on Fedora's default btrfs layout (which typically only splits
out `root` and `home`), not its own subvolume — check first:

```bash
sudo btrfs subvolume show /var/lib/docker
# "ERROR: not a btrfs subvolume" means it's a plain directory — conversion needed below.
# Any real output (a subvolume ID, path, etc.) means it's already its own
# subvolume — skip straight to the "quota enable + limit" commands.
```

**If it's a plain directory**, converting it to its own subvolume is a
one-time, disruptive migration (stops Docker, moves existing image/
container/volume data) — not something to run casually mid-session with
containers up. When ready:

```bash
sudo systemctl stop docker
sudo mv /var/lib/docker /var/lib/docker.bak
sudo btrfs subvolume create /var/lib/docker
sudo cp -a --reflink=always /var/lib/docker.bak/. /var/lib/docker/
# Verify the copy looks complete/sane before deleting the backup:
sudo du -sh /var/lib/docker /var/lib/docker.bak
sudo rm -rf /var/lib/docker.bak
sudo systemctl start docker
```

`--reflink=always` makes the copy near-instant and space-free on btrfs
(copy-on-write metadata clone, not a real data duplication) — if it's
slow, something's wrong (falling back to a real copy) and it's worth
stopping to check available disk space instead of waiting it out.

**Then, either way** (already a subvolume, or just converted):

```bash
sudo btrfs quota enable /var/lib/docker
sudo btrfs qgroup limit 50G /var/lib/docker
```

Verify:

```bash
sudo btrfs qgroup show -r /var/lib/docker   # -r shows the limit alongside current usage
```

Once the quota is hit, Docker gets disk-full errors from individual
operations (pulls, container writes) — same failure shape as the WSL2
VHDX section below, but contained to the 50GB ceiling instead of
consuming the whole root partition. `uv run homeserver.py gc` (prune +
compact — see below) is still the right periodic maintenance regardless
of whether a hard quota is set.

### Host inotify limits: hit when running many containers at once

A different axis from CPU/memory/disk above, and not something
`docker/docker-limits.py` touches — worth checking separately if
containers crash-loop or come up unhealthy right after a host reboot or a
`docker restart` of many containers at once (as opposed to steady-state
OOM/throttling, which the memory slice above already covers). Each
container's `containerd-shim` opens an inotify watch for OOM event
detection, and plenty of app images add their own file-watchers on top
(hot-reload, config/log tailing). Running enough containers concurrently
can exhaust the host's `fs.inotify.max_user_instances` — **128** by
default on Fedora and most distros — well before CPU or memory are
actually the bottleneck. Past that ceiling, `containerd` logs (but
doesn't itself crash on) errors like:

```text
failed to get memory.events watch FD: failed to create inotify fd: too many open files
```

Any container that relies on its own inotify watches during startup can
fail to come up cleanly or flap unhealthy right alongside those log
lines — a different failure mode from an actual memory/CPU shortage, so
it's worth ruling out on its own rather than assuming a bigger
`DOCKER_MEMORY_LIMIT` will fix it.

Raise it (`max_user_instances` is a separate, much lower-ceiling limit
than `max_user_watches` — raising the latter doesn't help here):

```bash
sudo sysctl -w fs.inotify.max_user_instances=1024   # takes effect immediately, no restart needed

# Persist across reboots:
sudo tee /etc/sysctl.d/99-docker-inotify.conf <<'EOF'
fs.inotify.max_user_instances=1024
EOF
sudo sysctl --system
```

Verify:

```bash
sysctl fs.inotify.max_user_instances
journalctl -u containerd --since "-5min" | grep -i "too many open files"   # should go quiet after raising
```

---

## Reclaiming disk space (Docker Desktop on Windows / WSL2)

Docker Desktop's WSL2 VHDX only grows, never shrinks automatically — even after you delete images/volumes, the backing disk file stays large until you reclaim it manually. Do this periodically if `C:` (or wherever the VHDX lives) is filling up.

**Automated (recommended):**

```bash
uv run homeserver.py gc          # prompts for confirmation first
uv run homeserver.py gc --yes    # skip the prompt
```

Runs `docker system prune -a --volumes -f` + `docker builder prune -a -f`, then on Windows also trims the WSL2 VM's filesystem (`fstrim -av`), shuts down WSL, and compacts the VHDX via `diskpart` — the same steps as the manual procedure below, in the right order. **Must be run from an Administrator terminal** for the compaction step to actually take effect — `diskpart` silently no-ops otherwise; the command detects this, skips compaction, and tells you to re-run elevated rather than pretending it worked. On native Linux Docker, pruning is the whole story (no VHDX involved) and it stops there. Prunes the whole Docker host, not just this stack — if other projects share this Docker install, their unused resources get pruned too, which is exactly why it asks for confirmation first.

**Manual, or if you want to understand/debug what the command above is doing:**

**1. Check what's actually using space, then prune.** Compacting only shrinks the file to match what's used *inside* it — pruning first is what makes compacting worthwhile:

```powershell
docker system df -v              # see what's using space, per image/container/volume
docker system prune -a --volumes -f
docker builder prune -a -f
wsl --shutdown
```

> `--volumes` deletes unnamed/anonymous volumes too — this is safe for build caches and dangling layers, but double-check you don't have unmounted named volumes here you still want.

**2. Find and check the current VHDX size.** The path/filename depends on Docker Desktop version:

- Newer (4.20+, WSL disk mount): `%LOCALAPPDATA%\Docker\wsl\disk\docker_data.vhdx`
- Older: `%LOCALAPPDATA%\Docker\wsl\data\ext4.vhdx`

```powershell
wsl --shutdown
Get-Item "$env:LOCALAPPDATA\Docker\wsl\disk\docker_data.vhdx" | Select-Object Name, @{N='SizeGB';E={[math]::Round($_.Length/1GB,2)}}
```

**3. Compact it via `diskpart`:**

```powershell
wsl --shutdown
diskpart
```

Inside the `diskpart` prompt:

```text
select vdisk file="C:\Users\<you>\AppData\Local\Docker\wsl\disk\docker_data.vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit
```

Then re-run the `Get-Item` check from step 2 to confirm it shrank.

**If `diskpart` barely shrinks it:** the newer `wsl\disk\` layout sometimes holds onto space more stubbornly than the older `ext4.vhdx` did. Export/reimport is more reliable there:

```powershell
wsl --shutdown
wsl --export docker-desktop-data "D:\docker-backup.tar"
wsl --unregister docker-desktop-data
wsl --import docker-desktop-data "C:\Docker\wsl-data" "D:\docker-backup.tar" --version 2
```

After reimporting, open Docker Desktop → **Settings → Resources → Advanced** and confirm the disk image location points at the new import path — some versions recreate a fresh VHDX at the default location on next launch instead of picking up the import.

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

[← Landing Page](07-landing.md) | [Home](../setup.md) | [Next: Firewall →](09-firewall.md)
