# 16 — MIN/CORE Reset Runbook

How the live MIN and CORE services were taken down, archived, healthcheck-audited, reset to empty installs one at a time, and restored with their data on 2026-10-03. Every command is listed in the order it ran, so the run can be repeated. It's for when you want proof that each service still installs cleanly from scratch *and* that its backups restore, without losing anything.

Above CORE the same was done without the restore step, since those apps held no data (see [08 — Maintenance](08-maintenance.md#fresh-start-of-a-service-reset)). For the individual commands, see [15 — Starting & Stopping Services](15-starting-services.md).

**Rules this runbook follows**
- One service at a time. Stateless services go first, light ones next, and the critical ones (Authentik, Immich, Nextcloud) last.
- Every healthcheck change is researched upstream first: the project's own compose, docs and image. See [10 — New Services](10-new-services.md) ("How fixes are chosen").
- Data is never deleted without a verified snapshot, and an off-machine copy is taken before starting.
- Docs and tests change together with each compose change.

## 0. Before starting

```bash
# Host disk healthy? (the 2026-10-02 freeze was the SSD dropping its link; see 08 "System freezes")
journalctl -k -b 0 | grep -c 'hard resetting link'          # must be 0
tuned-adm active                                             # balanced-nolpm
grep . /sys/class/scsi_host/host*/link_power_management_policy

# Repo consistent?
uv run pytest -q

# Off-machine drive mounted with room (each archive is about 25 GB)
df -h "/run/media/$USER/My Passport"
```

## 1. Stop everything and snapshot it

```bash
uv run homeserver.py prod down core     # CORE first; each running service is snapshotted as it stops
uv run homeserver.py prod down min
docker ps -q | wc -l                     # 0
```

Check that every service that holds data has today's snapshot. The ones without one should be stateless, with no volumes and no data folder:

```bash
uv run python -c "
import homeserver as hs
for s in hs.SERVICES_MIN + hs.SERVICES_CORE:
    sn = hs.list_snapshots(s); print(f'{s:13} {sn[-1].name if sn else \"-\"}')"

for s in cloudflared docs landing clamav whiteboard it-tools; do
  echo "$s vols=[$(docker volume ls -q --filter name=^${s}_ | tr '\n' ' ')] data=$(ls -d service_data/data/$s 2>/dev/null)"
done
```

## 2. Off-machine archive

```bash
uv run homeserver.py archive "/run/media/$USER/My Passport/homeserver-backup"
# -> homeserver-archive-<ts>.tar.gz (read back and verified) + .sha256
```

How to restore from it: [08 — Maintenance](08-maintenance.md#restoring-from-an-archive-new-machine-or-a-rebuilt-disk).

## 3. Healthcheck audit (research first)

List every MIN/CORE container with its image and current check:

```bash
uv run python - <<'EOF'
import yaml, homeserver as hs
for svc in hs.SERVICES_MIN + hs.SERVICES_CORE:
    doc = yaml.safe_load((hs.SERVICES_DIR/svc/hs.base_file(svc)).read_text()) or {}
    for name, d in (doc.get("services") or {}).items():
        hc = (d or {}).get("healthcheck") or {}
        t = hc.get("test"); t = " ".join(map(str, t)) if isinstance(t, list) else t
        print(f"{svc:13} {(d or {}).get('container_name', name):24} {t or '-'}")
EOF
```

See which images ship their own `HEALTHCHECK`. A compose `test:` replaces it:

```bash
docker image inspect <image> --format '{{if .Config.Healthcheck}}{{json .Config.Healthcheck}}{{else}}none{{end}}'
```

Then read upstream's own compose files and docs. These were fetched this time:

```bash
curl -fsSL https://raw.githubusercontent.com/goauthentik/authentik/main/lifecycle/container/compose.yml
curl -fsSL https://github.com/immich-app/immich/releases/latest/download/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/plausible/community-edition/master/compose.yml
curl -fsSL https://raw.githubusercontent.com/louislam/uptime-kuma/master/compose.yaml
curl -fsSL https://raw.githubusercontent.com/louislam/uptime-kuma/2.5.5/docker/dockerfile | grep HEALTHCHECK
curl -fsSL https://raw.githubusercontent.com/wg-easy/wg-easy/master/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/firefly-iii/docker/main/docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/henrygd/beszel-docs/main/en/guide/healthchecks.md
curl -fsSL https://raw.githubusercontent.com/plausible/analytics/v3.2.1/lib/plausible_web/router.ex | grep health
```

### What changed

| Change | Containers | Why |
|---|---|---|
| Compose check removed, image's own `HEALTHCHECK` used | uptime-kuma, authentik-server, firefly, firefly-importer, immich-db, atuin, whiteboard, mailpit | Upstream's compose defines none, and the image ships one |
| Image check kept, only timing overridden (no `test:`) | guacd, wg-easy, vaultwarden | The image's first check came a full interval (60s–5min) after start, holding back dependants. Now `start_period` + `start_interval: 2s` |
| Endpoint updated | plausible: `/api/health` → `/api/system/health/ready` | Plausible's router marks the old path for removal |
| Upstream's exact check | authentik-db | `pg_isready -d … -U …`, 30s/5s/5/20s |
| `pg_isready -h 127.0.0.1` (TCP) | every MIN/CORE `*-db`, shared-postgres | On a fresh volume the image's socket-only init server passes a socket probe, so apps then hit `connection refused` ([postgresql.org BUG #15222](https://postgresql.org/message-id/152778474106.26722.11024944991637906220%40wrigleys.postgresql.org)) |
| `start_period` + `start_interval: 2s` | MIN/CORE databases and redis | The first check comes within seconds instead of after `interval` (atuin 70s → 13s) |
| `clamav-watchdog` removed | clamav | Uptime Kuma already marks an `unhealthy` container DOWN and alerts via ntfy (upstream `server/model/monitor.js`). Alert credentials moved to `services/ntfy/.env` |
| Repairs alert via ntfy | adguard-watchdog | Every network repair is now announced. If none arrive for weeks after the boot-safety fix, it can go |

Enforced by `tests/test_healthchecks.py`: `IMAGE_HEALTHCHECK`, `NO_HEALTHCHECK` and `test_pg_isready_probes_tcp_not_the_socket`.

```bash
docker compose --env-file .env --env-file services/<svc>/.env -f services/<svc>/compose.yml config -q   # each changed file
uv run pytest -q
```

## 4. Reset → check → restore → check, per service

This is the cycle used for every service. It's saved as a throwaway script; nothing in the repo depends on it:

```bash
cat > /tmp/cycle.sh <<'EOF'
#!/usr/bin/env bash
# reset -> fresh health -> restore reset-backup -> health.  Usage: [EXTRA='a|b'] cycle.sh <svc>
s=$1; cd ~/homeserver            # repo root
clean() { sed 's/\x1b\[[0-9;]*m//g'; }
health() { docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -E "^$s(-|	)|^($2)	" | sed 's/^/    /'; }
T=$(date +%s)
out=$(timeout 1800 uv run homeserver.py prod reset $s -y 2>&1 | clean)
snap=$(echo "$out" | grep -oE 'reset-backup-[0-9]{8}-[0-9]{6}' | tail -1)
echo "== $s RESET ($(( $(date +%s)-T ))s) snapshot=$snap"
echo "$out" | grep -E 'ready \(|✖|ERROR|not healthy|timed out|unhealthy' | sed 's/^/    /'
health "$s" "${EXTRA:-zzz}"
[ -n "$snap" ] || { echo "    NO reset-backup found -- stopping"; exit 1; }
T=$(date +%s)
out=$(timeout 1800 uv run homeserver.py prod restore $s --snapshot $snap 2>&1 | clean)
echo "== $s RESTORE ($(( $(date +%s)-T ))s)"
echo "$out" | grep -E 'restored|ready \(|✖|ERROR|failed|not healthy|timed out' | sed 's/^/    /'
health "$s" "${EXTRA:-zzz}"
EOF
chmod +x /tmp/cycle.sh
```

What it runs for each service:

```bash
uv run homeserver.py prod reset <svc> -y                                  # verified snapshot kept as reset-backup-<ts>, wipe, start empty
docker ps -a --format '{{.Names}}\t{{.Status}}' | grep <svc>              # every container healthy on the empty install?
uv run homeserver.py prod restore <svc> --snapshot reset-backup-<ts>      # data back
docker ps -a --format '{{.Names}}\t{{.Status}}' | grep <svc>              # healthy again?
```

Order used. Stateless services (reset only, nothing to restore):

```bash
uv run homeserver.py prod reset docs -y      # also starts wg-easy first (prod binds 10.8.0.1)
for s in landing cloudflared it-tools whiteboard clamav; do uv run homeserver.py prod reset $s -y; done
```

Services with data:

```bash
/tmp/cycle.sh beszel
for s in ntfy mailpit atuin uptime-kuma adguard-home; do /tmp/cycle.sh $s; done
EXTRA=guacd /tmp/cycle.sh guacamole
for s in plausible forgejo nginx-plain portainer wg-easy vaultwarden; do /tmp/cycle.sh $s; done
EXTRA='firefly-cron|firefly-importer' /tmp/cycle.sh firefly     # firefly-importer lives in firefly's compose
for s in onlyoffice jellyfin authentik immich nextcloud; do /tmp/cycle.sh $s; done
```

After changing a healthcheck mid-run, re-check it with a restart and time it:

```bash
S=$(date +%s); uv run homeserver.py prod restart wg-easy; echo "took $(( $(date +%s)-S ))s"
docker inspect wg-easy --format '{{.State.Health.Status}} {{json .Config.Healthcheck}}'
docker inspect <ctr> --format '{{range .State.Health.Log}}{{.Start}} rc={{.ExitCode}} {{.Output}}{{println}}{{end}}'
```

Before resetting Immich and Nextcloud, confirm their user files live outside what `reset` wipes. It never touches secondary roots:

```bash
grep -E '^(UPLOAD_LOCATION|USER_DATA_ROOT|OS_ISO_ROOT)=' services/immich/.env services/nextcloud/.env   # on /mnt/media
grep -vE '^\s*#|^\s*$' services/nextcloud/hooks/before-starting/*                                      # no hook touches them
```

## 5. Data checks after each restore

The `.env` values are read in place and never printed (`e svc KEY`):

```bash
e(){ grep "^$2=" services/$1/.env | cut -d= -f2-; }

# beszel: the agent reconnects to the restored hub (its key is accepted)
docker logs beszel-agent 2>&1 | grep 'WebSocket connected'
# atuin
docker exec atuin-db psql -h 127.0.0.1 -U $(e atuin POSTGRES_USER) -d $(e atuin POSTGRES_DB) -tAc 'select count(*) from users'
# uptime-kuma (and that a clamav monitor exists, since it replaces clamav-watchdog)
q(){ docker exec -e MYSQL_PWD="$(e uptime-kuma MYSQL_PASSWORD)" uptime-kuma-db mariadb -u"$(e uptime-kuma MYSQL_USER)" "$(e uptime-kuma MYSQL_DATABASE)" -N -e "$1"; }
q 'select count(*) from monitor'; q "select name,active from monitor where docker_container='clamav'"
# adguard-home answers DNS
dig +short @$(e adguard-home DNS_BIND_IP) example.com
# forgejo / guacamole / plausible
docker exec forgejo-db psql -h 127.0.0.1 -U $(e forgejo POSTGRES_USER) -d $(e forgejo POSTGRES_DB) -tAc 'select count(*) from repository'
docker exec guacamole-db psql -h 127.0.0.1 -U $(e guacamole POSTGRES_USER) -d $(e guacamole POSTGRES_DB) -tAc 'select count(*) from guacamole_connection'
docker exec plausible-db psql -U postgres -d plausible -tAc 'select count(*) from sites'
docker exec plausible-events-db clickhouse-client -q 'select count() from plausible_events_db.events_v2'
# vaultwarden (SQLite, read through a throwaway container)
docker run --rm -v "$(readlink -f service_data)/data/vaultwarden/data:/d:ro" alpine:3.24.2 \
  sh -c 'apk add -q sqlite >/dev/null; sqlite3 /d/db.sqlite3 "select count(*) from users; select count(*) from ciphers;"'
# firefly / wg-easy / jellyfin
docker exec firefly-db psql -h 127.0.0.1 -U $(e firefly POSTGRES_USER) -d $(e firefly POSTGRES_DB) -tAc 'select count(*) from transactions'
docker exec wg-easy sh -c 'wg show wg0 peers | wc -l'
curl -s http://127.0.0.1:8096/System/Info/Public | grep -o '"StartupWizardCompleted":[a-z]*'
# authentik
docker exec authentik-db psql -h 127.0.0.1 -U $(e authentik POSTGRES_USER) -d $(e authentik POSTGRES_DB) \
  -tAc 'select count(*) from authentik_core_user; select count(*) from authentik_core_application;'
# immich (photos + public URL)
docker exec immich-db psql -U $(e immich DB_USERNAME) -d $(e immich DB_DATABASE_NAME) -tAc 'select count(*) from asset; select count(*) from "user";'
curl -s -o /dev/null -w '%{http_code}\n' https://immich.$(grep ^DOMAIN= .env | cut -d= -f2)/api/server/ping
# nextcloud
docker exec nextcloud curl -s http://localhost/status.php                     # "installed":true
docker exec -u www-data nextcloud php occ user:list
docker exec -u www-data nextcloud php occ files_external:list
docker exec -u www-data nextcloud php occ config:app:get onlyoffice DocumentServerUrl
# anything not healthy (watchdogs/cron/runners/portainer have no check by design)
docker ps --format '{{.Names}}\t{{.Status}}' | grep -v healthy
```

## 6. Results (2026-10-03)

| Service | Empty install | Restored data |
|---|---|---|
| docs, landing, cloudflared, it-tools, whiteboard, clamav | healthy in 5–10s | stateless |
| beszel | healthy | the agent reconnected to the hub |
| ntfy, mailpit, nginx-plain, onlyoffice | healthy in 5s | restored, healthy |
| portainer | running (no check by design) | restored |
| atuin | healthy, 70s → 13s after the DB `start_interval` | user account |
| uptime-kuma | healthy | 187 monitors, including `clamav` |
| adguard-home | healthy | answering DNS |
| guacamole | healthy | 3 connections |
| plausible | healthy in 20s | 2 sites, 687 events |
| forgejo | healthy | 3 repositories |
| wg-easy | healthy, 60s → 5s | both peers, original server keys |
| vaultwarden | healthy, 60s → 5s after the timing fix | 2 users, 317 vault items |
| firefly | healthy | 1,576 transactions |
| jellyfin | healthy in 10s | setup completed, config intact |
| authentik | healthy in 50s (first migrations) | 4 users, 2 applications |
| immich | healthy in 30s | 21,246 assets, 2 users, public URL 200 |
| nextcloud | healthy in 20s | installed, users, `/OS-ISOs` external storage, OnlyOffice connection, public URL 200 |

No SATA link errors during the run (`journalctl -k -b 0 | grep -c 'hard resetting link'` → 0).

**Afterwards:**
- Delete the stale `clamav-watchdog` monitor in Uptime Kuma (**open the monitor → Delete**). The container no longer exists.
- Each service keeps its `reset-backup-<ts>` folder: the newest 5 per service are kept, outside normal retention. To go back to any of them, run `restore <svc> --snapshot reset-backup-<ts>`.

---

[← Starting & Stopping Services](15-starting-services.md) | [Home](../setup.md)
