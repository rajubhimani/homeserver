# Firefly III (+ Data Importer)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Personal finance manager — income, expenses, budgets, accounts, recurring transactions.
**Port:** `8102` (host) → `8080` (container) | **Data:** `service_data/data/firefly/` (app storage) + named volume `firefly-postgres-alpine` (DB) | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~141MB total (importer 59 + cron 2 + app 74 + db 6)

## Setup

```bash
cp services/firefly/.env.example services/firefly/.env
# APP_KEY: openssl rand -hex 16  (exactly 32 chars)
# STATIC_CRON_TOKEN: openssl rand -hex 16  (exactly 32 chars)
# set POSTGRES_PASSWORD and SITE_OWNER
mkdir -p service_data/data/firefly/storage/{framework/{cache/data,sessions,views},logs,app/public,upload}
uv run homeserver.py dev up firefly
# One-time only — see "OAuth keys" below before ever re-running this
docker exec -it firefly php artisan passport:install --force   # Docker
podman exec -it firefly php artisan passport:install --force   # Podman
# Keys are created as root — make them readable by www-data (PHP process)
chmod 644 service_data/data/firefly/storage/oauth-private.key service_data/data/firefly/storage/oauth-public.key
```

**OAuth keys — do not re-run `passport:install --force` casually.** Keys are stored in `service_data/data/firefly/storage/` and persist across restarts, so the command above only needs to run once, on the very first start. **Running `--force` again rotates the keys and logs everyone out.**

## First login

Browse to `http://<ip>:8102` — the **first registration becomes admin**. Disable further signups at Administration → `/settings/configuration`.

## Notes

- `APP_KEY` and `STATIC_CRON_TOKEN` must each be **exactly 32 characters**
- `APP_URL` must be `https://firefly.${DOMAIN}` and `TRUSTED_PROXIES` must be `"**"` — both required by Firefly III's own docs for it to generate `https://` links instead of `http://` (a mismatched scheme gets blocked by the browser's CSP `connect-src`, e.g. on the transaction-delete API call)
- Includes an alpine `firefly-cron` container that triggers recurring transactions daily at 03:00

## Data Importer

**Port:** `8104` — starts automatically alongside Firefly.

One-time setup after Firefly III is running:

1. Firefly III → Profile → OAuth → **OAuth Clients** → Create new client
2. Redirect URL: `https://firefly-import.yourdomain.com/callback` — uncheck "Keep a secret?"
3. Copy the resulting **Client ID** (a UUID like `019f0fc9-379d-73bf-bc43-7ec7c6fb4ac9`)
4. Set `FIREFLY_III_CLIENT_ID=<uuid>` in `services/firefly/.env` and restart the importer:

   ```bash
   uv run homeserver.py prod up firefly
   ```

This pre-fills the Client ID for all users. Each user then authenticates with their own Firefly III account via OAuth — no shared token needed. Browse to `https://firefly-import.yourdomain.com` to import CSV, YNAB exports, or connect bank accounts via Nordigen.

## Troubleshooting: `firefly-db` crash-loops with `PANIC: could not locate a valid checkpoint record`

This means the WAL (write-ahead log) is corrupted — usually from an interrupted copy/migration of the volume, an unclean host shutdown, or disk issues. It is **not** the same as `FATAL: data directory has wrong ownership` (a permissions problem, not corruption) — check `docker logs firefly-db` for the exact message first.

**Before doing anything else, check whether the last shutdown was clean:**

```bash
docker logs firefly-db 2>&1 | grep "database system was"
```

- `database system was shut down at ...` (clean) → recovery below is low-risk; all committed data was already flushed to disk before the WAL got corrupted afterward.
- `database system was interrupted; last known up at ...` (crash) → recovery is lossier; anything after that timestamp may be gone regardless of method.

**Recovery — always validate on a disposable copy first, never the live volume directly:**

```bash
# 1. Copy the corrupted volume to a scratch volume and try pg_resetwal there
docker volume create firefly-recovery-test
docker run --rm -v firefly_firefly-postgres-alpine:/from:ro -v firefly-recovery-test:/to alpine:3.24.1 sh -c "cp -a /from/. /to/"
docker run --rm -u 999:999 -v firefly-recovery-test:/var/lib/postgresql postgres:18.4 pg_resetwal -f /var/lib/postgresql/18/docker

# 2. Boot postgres against the scratch copy and verify with pg_dump — not just SELECT count(*),
#    which can look fine while page-level corruption still exists
docker run -d --name firefly-recovery-test -v firefly-recovery-test:/var/lib/postgresql -e POSTGRES_DB=firefly -e POSTGRES_USER=firefly -e POSTGRES_PASSWORD=test postgres:18.4
docker exec firefly-recovery-test pg_dump -U firefly -d firefly -f /tmp/dump.sql && echo OK

# 3. Only once that validates cleanly: back up the real volume, then apply the same fix to it
docker run --rm -v firefly_firefly-postgres-alpine:/from:ro -v "$(pwd)/service_data/backup/firefly:/backup" alpine:3.24.1 sh -c "tar czf /backup/firefly-postgres-precorrupt.tar.gz -C /from ."
docker run --rm -u 999:999 -v firefly_firefly-postgres-alpine:/var/lib/postgresql postgres:18.4 pg_resetwal -f /var/lib/postgresql/18/docker

# 4. Clean up the scratch volume/container
docker rm -f firefly-recovery-test
docker volume rm firefly-recovery-test
```

Verify row counts (accounts/transactions/users) after bringing `firefly-db` back up match what you expect before trusting it.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
