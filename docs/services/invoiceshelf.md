# InvoiceShelf

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Open-source invoicing and billing — the actively maintained community successor to Crater (same Laravel + MariaDB stack, same data format; the original `foralabs/crater` image was made private).
**Port:** `8101` (host) → `8080` (container) | **Data:** `service_data/data/invoiceshelf/` | **Requires:** MariaDB | **Memory:** no hard limit set; measured idle ~172MB total (app 63 + db 109)

## Setup

`compose.yml` bind-mounts the *entire* `/var/www/html/storage` directory (`${DATA_ROOT}/uploads:/var/www/html/storage`), which hides the subdirectories Laravel needs (`framework/cache`, `framework/sessions`, `app/templates/pdf`, etc.) that the image normally ships pre-populated — the container's own entrypoint doesn't recreate them on its own. **Fixed permanently, no manual step needed**: `services/invoiceshelf/entrypoint.d/10-ensure-storage-dirs.sh` creates all ten required subdirectories (same `serversideup/php` `/etc/entrypoint.d/*` mechanism as the `.env`-permission fix below, run in filename order on every container start before the app boots) — confirmed live by wiping `service_data/data/invoiceshelf/uploads/` completely and running `up --fresh` twice in a row, both times booting clean with zero manual intervention. Before this existed, skipping a manual pre-create step failed first boot with `Please provide a valid cache path` / `The "/var/www/html/storage/app/templates/pdf" directory does not exist` and a restart loop — this is why the fix specifically targets *every* directory in that list, not only `templates/pdf` (the one that happens to fail loudly at boot; the others fail more quietly later, e.g. a broken upload, rather than blocking startup at all).

**`.env` write-permission gotcha (fixed, but know why)**: `/var/www/html/.env` ships root-owned (`644`) in this image, but the process that actually handles HTTP requests runs as `www-data` (php-fpm's worker pool — the container's own top-level process is root, but that's not who serves requests). `www-data` can read `.env` but not write it, which makes the web install wizard's "database config" step fail with a generic "cannot write configuration" error — it needs to persist DB settings back into `.env`. Since `.env` isn't on a mounted volume, a one-off `docker exec chown` fix doesn't survive a recreate. Fixed permanently via `services/invoiceshelf/entrypoint.d/99-fix-env-permissions.sh`, mounted into `/etc/entrypoint.d/` — `serversideup/php` images (this one included) run every script there, in order, on **every** container start before the app boots, which is the image's own documented extension point for exactly this kind of startup fixup.

**"Database should be empty" / connection errors during the install wizard**: the image auto-runs `php artisan migrate` on every container boot by default (`serversideup/php`'s "Laravel automations" entrypoint, gated by `AUTORUN_ENABLED=true`). That races the web wizard — migrations populate the full schema before the wizard ever runs, so its "database must be empty" precondition fails even though `users`/`companies`/`invoices` are all still empty. InvoiceShelf's own official `docker-compose` disables this for exactly this reason. Fixed via `AUTORUN_LARAVEL_MIGRATION=false` in `.env` — the wizard is what's supposed to run migrations, not the boot automation. If you hit this before the fix was in place, the DB needs manually emptying once: `docker exec invoiceshelf php artisan db:wipe --force` (drops all tables without re-running migrations; safe since nothing had real data yet — check `SELECT COUNT(*) FROM users` etc. first if unsure).

**"Domain verification failed. Please enter valid domain name." during the install wizard**: the underlying cause has nothing to do with the domain being invalid — it's a Laravel Sanctum config gap. The image's own default `.env` ships a blank `SANCTUM_STATEFUL_DOMAIN` (**singular** — not a real Laravel Sanctum config key at all, so it's silently ignored; the real one is plural, `SANCTUM_STATEFUL_DOMAINS`). Without it set to the actual public host, the wizard's login step succeeds (200 + session cookie issued) but the very next auth-check request gets rejected as coming from an untrusted domain — the wizard surfaces that as a generic domain-verification failure. Fixed in `compose.yml`'s `environment:` block: `SANCTUM_STATEFUL_DOMAINS` and `SESSION_DOMAIN` both set to `invoiceshelf.${DOMAIN}` (matching `APP_URL`'s host, no scheme).

```bash
cp services/invoiceshelf/.env.example services/invoiceshelf/.env
# generate: echo "base64:$(openssl rand -base64 32)" → APP_KEY
# set MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD

uv run homeserver.py dev up invoiceshelf
```

No manual pre-create step needed — `entrypoint.d/10-ensure-storage-dirs.sh` handles the required `storage/` subdirectories automatically on every start, including a bare `--fresh` restart later (see note above).

## First login

Browse to `http://<ip>:8101` — the setup wizard creates the admin account.

**Database step of the wizard:** it pre-fills **Database Host as `127.0.0.1`**, which doesn't work — nothing listens on `127.0.0.1:3306` inside the app container; MariaDB is a separate container reached by its Docker network name. Leaving the default produces `SQLSTATE[HY000] [2002] Connection refused`. Enter these instead:

| Field | Value |
| --- | --- |
| Database Host | `invoiceshelf-db` |
| Database Port | `3306` |
| Database Name | `MYSQL_DATABASE` from `.env` (default `invoiceshelf`) |
| Database Username | `MYSQL_USER` from `.env` (default `invoiceshelf`) |
| Database Password | `MYSQL_PASSWORD` from `.env` |

**Mail Configuration step of the wizard:** no real mail provider is configured for this service, so point it at `mailpit` (already running in this stack) instead of leaving it blank or guessing at real SMTP credentials — every email InvoiceShelf sends (invites, invoice PDFs, password resets) lands in mailpit's web inbox at `mailpit.${DOMAIN}` rather than actually being delivered, which is enough to click through links during setup/testing:

| Field | Value |
| --- | --- |
| Mail Driver / Mailer | SMTP |
| Host | `mailpit` |
| Port | `1025` |
| Encryption | None |
| Username / Password | leave blank — mailpit accepts unauthenticated mail |
| From Address | anything, e.g. `noreply@${DOMAIN}` |

Swap these for real SMTP credentials in `services/invoiceshelf/.env` later if actual email delivery is needed.

**Stuck on a spinner after login, or F5 bounces straight back to `/login`**: before chasing `SESSION_DOMAIN`/`SANCTUM_STATEFUL_DOMAINS`/cookie config server-side, first clear cookies and cached assets for `invoiceshelf.${DOMAIN}` (or just try a fresh incognito window) and log in again. Multiple failed installs/logins during development (wrong DB host, non-empty database, etc.) leave behind stale session cookies from earlier attempts that the browser keeps resending alongside the new one, confusing the SPA's auth check even though the server-side session/cookie config is correct. This has been the actual cause every time this symptom came up here — the server-side config below was already right.

## Using it day to day

- **Clients → Invoices/Estimates** is the core flow: create a client first, then an invoice or estimate against them. Estimates can be converted directly into an invoice once accepted, rather than re-entering line items.
- **Company settings** (logo, currency, tax rates, invoice number format) apply per-company if multiple companies are set up — InvoiceShelf supports more than one business under one login.
- **Mobile app:** InvoiceShelf publishes mobile app source (React Native/Expo, [GitHub](https://github.com/InvoiceShelf/mobile)) but this wasn't confirmed to be published as a ready-to-install app on Google Play/App Store — treat this deployment as web-only (`https://invoiceshelf.${DOMAIN}`) unless you independently confirm a current store listing.

## Health endpoint

`services/invoiceshelf/compose.yml`'s healthcheck on the app container hits `http://localhost:8080/` (root path, plain `curl -f`) — a 200 there is enough to be marked healthy, no dedicated `/health` route.

## Notes

- Image: `invoiceshelf/invoiceshelf`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
