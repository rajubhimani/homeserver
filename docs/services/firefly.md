# Firefly III (+ Data Importer)

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Personal finance manager — income, expenses, budgets, accounts, recurring transactions.
**Port:** `8102` (host) → `8080` (container) | **Data:** `service_data/firefly/` | **Requires:** Postgres

## Setup

```bash
cp firefly/.env.example firefly/.env
# APP_KEY: openssl rand -hex 16  (exactly 32 chars)
# STATIC_CRON_TOKEN: openssl rand -hex 16  (exactly 32 chars)
# set POSTGRES_PASSWORD and SITE_OWNER
mkdir -p service_data/firefly/postgres
mkdir -p service_data/firefly/storage/{framework/{cache/data,sessions,views},logs,app/public,upload}
sh homeserver.sh dev up firefly
# One-time: seed OAuth keys into persistent storage (required on first start)
docker exec -it firefly php artisan passport:install --force   # Docker
podman exec -it firefly php artisan passport:install --force   # Podman
# Keys are created as root — make them readable by www-data (PHP process)
chmod 644 service_data/firefly/storage/oauth-private.key service_data/firefly/storage/oauth-public.key
```

## First login

Browse to `http://<ip>:8102` — the **first registration becomes admin**. Disable further signups at Administration → `/settings/configuration`.

## Notes

- `APP_KEY` and `STATIC_CRON_TOKEN` must each be **exactly 32 characters**
- `APP_URL` must be `https://firefly.${DOMAIN}` and `TRUSTED_PROXIES` must be `"**"` — both required by Firefly III's own docs for it to generate `https://` links instead of `http://` (a mismatched scheme gets blocked by the browser's CSP `connect-src`, e.g. on the transaction-delete API call)
- Includes an alpine `firefly-cron` container that triggers recurring transactions daily at 03:00

## OAuth keys — do not re-run `passport:install --force` casually

Keys are stored in `service_data/firefly/storage/` and persist across restarts — `passport:install --force` only needs to be run once, on the very first start. After that, restarts never regenerate the keys, so existing sessions and JWTs stay valid. **Running `--force` again rotates the keys and logs everyone out.**

```bash
# Docker
docker exec -it firefly php artisan passport:install --force
# Podman
podman exec -it firefly php artisan passport:install --force
```

## Data Importer

**Port:** `8104` — starts automatically alongside Firefly.

One-time setup after Firefly III is running:

1. Firefly III → Profile → OAuth → **OAuth Clients** → Create new client
2. Redirect URL: `https://firefly-import.yourdomain.com/callback` — uncheck "Keep a secret?"
3. Copy the resulting **Client ID** (a UUID like `019f0fc9-379d-73bf-bc43-7ec7c6fb4ac9`)
4. Set `FIREFLY_III_CLIENT_ID=<uuid>` in `firefly/.env` and restart the importer:
   ```bash
   sh homeserver.sh prod up firefly
   ```

This pre-fills the Client ID for all users. Each user then authenticates with their own Firefly III account via OAuth — no shared token needed. Browse to `https://firefly-import.yourdomain.com` to import CSV, YNAB exports, or connect bank accounts via Nordigen.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
