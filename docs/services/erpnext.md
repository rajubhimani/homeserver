# ERPNext

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Full open-source ERP (the Frappe framework's flagship app) — accounting, per-customer/supplier running credit-debit ledger (**Party Ledger**, under Accounts Receivable/Payable), invoicing, and inventory. This is the closest self-hostable equivalent to apps like Khatabook/Vyapar for tracking who owes you money and who you owe — plus a lot more that those apps don't do.
**Port:** `8153` (host) → `8080` (container, the `erpnext` frontend/nginx container) | **Data:** `service_data/data/erpnext/` | **Requires:** MariaDB, two Redis instances (all bundled in this stack) | **Memory:** not yet measured live — this is a genuinely heavy multi-container stack (9 containers: db, 2x redis, configurator, backend, frontend, websocket, 2x queue worker, scheduler), expect noticeably more than InvoiceShelf or Firefly III.

## Why ERPNext and not Frappe Books

[Frappe Books](https://github.com/frappe/books) has the same Party Ledger concept and is lighter, but it's a **desktop-only Electron app** with local SQLite storage — it has no server/API mode and can't be deployed as a Docker service on this homeserver, and critically it has **no Android app**. ERPNext is the web-based sibling built on the same Frappe framework: it runs as a proper multi-user server here, is reachable from any browser, and has an official Android app (**ERPNext Mobile** on Google Play, also works with the community **Appe** app) that connects to this self-hosted instance directly — no cloud dependency.

## Setup

```bash
cp services/erpnext/.env.example services/erpnext/.env
# set DB_PASSWORD (MariaDB root password) and ERPNEXT_ADMIN_PASSWORD
# (the site's Administrator login, used when the site is first created)

uv run homeserver.py dev up erpnext
```

This brings up 10 containers (including the one-shot `erpnext-create-site`, below): `erpnext-db` (MariaDB), `erpnext-redis-cache`, `erpnext-redis-queue`, `erpnext-configurator` (one-shot — writes DB/Redis connection info into the shared `sites` volume, then exits), `erpnext-backend` (Gunicorn), `erpnext-websocket`, `erpnext-queue-short`, `erpnext-queue-long`, `erpnext-scheduler`, and `erpnext` itself (the nginx frontend everything else sits behind — this is the one `nginx-plain` proxies to and the one with the published port).

**The site is created automatically on first boot.** Frappe/ERPNext keeps each site in the `erpnext-sites` volume, so a fresh install (or a `reset`) has no site until one is made. The one-shot `erpnext-create-site` container does it: it waits for MariaDB and both Redis containers, then runs `bench new-site --install-app erpnext --set-default erpnext.${DOMAIN}`, using `DB_PASSWORD` as the MariaDB root password and `ERPNEXT_ADMIN_PASSWORD` for the `Administrator` login. It skips straight away when the site already exists, so every later `up` is unaffected. The `erpnext` front container only starts after it succeeds, so its health check never runs against a site-less install. The first run takes a few minutes (it installs ERPNext's full schema and fixtures). This is adapted from frappe_docker's own `pwd.yml` `create-site` service (added 2026-10-02; before that it was a manual `bench new-site` after every wipe).

**Public hostname (prod):** the Cloudflare tunnel is dashboard-managed, so `erpnext.${DOMAIN}` returns a Cloudflare **502** until you add it: [one.dash.cloudflare.com](https://one.dash.cloudflare.com) → Networks → Tunnels → this tunnel → **Public Hostname** → add `erpnext.${DOMAIN}` → `http://nginx-plain:80` (see [cloudflared's doc](cloudflared.md)). nginx-plain's `erpnext` vhost only takes effect after nginx-plain restarts (`uv run homeserver.py prod up nginx-plain`).

**PDFs:** the default `wkhtmltopdf` generator fetches the page's own CSS over HTTP from the site URL, so until the public hostname above resolves end-to-end it fails with `wkhtmltopdf reported an error: Exit with code 1 due to network error: ConnectionRefusedError`. v16's Chrome generator (`pdf_generator=chrome`, per print format) doesn't have that dependency and works out of the box via the `chromium_path` the configurator sets — verified 2026-09-25 on v16.36.0.

**Setup wizard enables the scheduler:** `bench new-site` ends with `*** Scheduler is disabled ***` — expected; background jobs start once the first-login setup wizard below is completed.

## First login

Browse to `http://<ip>:8153` (dev) or `https://erpnext.${DOMAIN}` (prod, once `nginx-plain`/Cloudflare routing is in place — see [nginx-plain's own doc](nginx-plain.md) if unsure). Log in as `Administrator` with the `--admin-password` chosen above. ERPNext's own setup wizard runs on first login (company name, country, currency, chart of accounts) — this is separate from and after the `bench new-site` step, and only configures the app, not the database.

## Administrator and admin users

**The `Administrator` account is created with `ERPNEXT_ADMIN_PASSWORD` from `services/erpnext/.env`** (by `erpnext-create-site` on a fresh install). Changing the `.env` value later does nothing to an existing site: change it in the UI or with `set-admin-password` below, and keep `.env` in step if you want a future fresh install to use the same password. Change it later from the UI: avatar (top right) → **My Settings** → **Change Password**.

All commands below run against the live site from the host — no old password needed. `<site>` is `erpnext.${DOMAIN}` with the real domain substituted (e.g. `erpnext.example.com`); `-it` is only there so a password prompt works if you leave the password argument out.

```bash
# Reset the Administrator password (lost/forgotten)
docker exec -it erpnext-backend bench --site <site> set-admin-password '<new-password>'

# Create a named admin account for day-to-day use (full System Manager rights)
docker exec -it erpnext-backend bench --site <site> add-system-manager you@example.com \
  --first-name You --last-name Name --password '<password>'

# Reset any other user's password (add --logout-all-sessions to kick existing logins)
docker exec -it erpnext-backend bench --site <site> set-password you@example.com '<new-password>'
```

**Prefer a named System Manager over `Administrator` for daily work** — `Administrator` is Frappe's built-in superuser (bypasses all permission checks, can't be disabled or deleted), and a named account keeps an audit trail of who changed what. Keep `Administrator` for recovery. Adding staff through the UI instead: search **User** → **Add User** → set email/name → **Roles** (e.g. System Manager, Accounts User, Sales User) → Save; they get an email to set their own password once outgoing email is configured.

Note: quotes around passwords matter — a `$` or `!` inside double quotes gets expanded by the host shell before it reaches `bench`.

## Using the Party Ledger (the Khatabook-equivalent workflow)

1. **Accounting → Chart of Accounts / Customer / Supplier**: create a customer (or supplier) record for each person/business you extend credit to or receive credit from.
2. Every invoice, payment entry, credit note, or journal entry you post against that customer/supplier updates their running balance automatically — this *is* the udhaar/khata ledger, just modeled as double-entry accounting under the hood instead of a flat give/take list.
3. **Accounting → Reports → Accounts Receivable / Accounts Payable → Party Ledger**: pick a customer or supplier and date range to see the full running balance history — the direct equivalent of opening someone's page in a khata app.
4. Payment reminders aren't a single toggle like Khatabook's — they're built via ERPNext's **Notification** doctype (Setup → Notification) or the **Dunning** feature under Accounts Receivable for overdue-invoice reminders. More setup than Khatabook's built-in reminder button, but scriptable/schedulable once configured.

## Android app

Install **ERPNext Mobile** (`com.createchsoft.erpnextmobile` on Google Play) or the community **Appe** app, and point it at `https://erpnext.${DOMAIN}` with the same login used on desktop. Both are third-party-maintained clients that talk to any self-hosted Frappe/ERPNext site over its REST API — not Frappe's own first-party app, so treat login issues as a mobile-app-specific troubleshooting path (check the app's own docs/forum thread) rather than an ERPNext server misconfiguration first.

## Health endpoint

`services/erpnext/compose.yml`'s healthcheck on the `erpnext` (frontend) container hits `http://localhost:8080/api/method/ping` — this is Frappe's standard unauthenticated liveness endpoint (returns `{"message":"pong"}`), not a generic root-path check. Backend and websocket use the image's own `wait-for-it` on their ports (8000 / 9000), as community frappe_docker setups do; both Redis containers use `redis-cli ping`. The queue workers and scheduler have no listener to probe and deliberately have no check.

## Notes

- Image: `frappe/erpnext` — pin the tag in `.env` (`ERPNEXT_VERSION`); check [Docker Hub tags](https://hub.docker.com/r/frappe/erpnext/tags) before bumping, since major-version jumps (`v14` → `v15`) need ERPNext's own release notes read first. After *any* tag bump (even a minor like `v16.36.0` → `v16.37.0`), run `docker exec erpnext-backend bench --site all migrate` once the new containers are up — nothing in `compose.yml` runs it automatically (the configurator only writes connection config). Pinned to `v16.37.0` (bumped 2026-09-30 from `v16.36.0`, which matched upstream `frappe_docker`'s `example.env` as of 2026-09-23). Redis is `valkey/valkey:9.1.2-alpine` (cache and queue) since 2026-10-03. Frappe's own Helm chart deploys Valkey and Frappe is moving to it from v16 ([frappe_docker#1364](https://github.com/frappe/frappe_docker/issues/1364)); it also matches what AWS ElastiCache and GCP Memorystore run ([managed-cloud parity](../10-new-services.md#managed-cloud-parity-orchestrators-and-backing-services)). Valkey can't read Redis 8's RDB files, so the queue moved to a fresh volume (`erpnext-valkey-queue-data`); the old `erpnext-redis-queue-data` stays in the snapshots.
- This stack mirrors the official [frappe_docker](https://github.com/frappe/frappe_docker) production compose + MariaDB/Redis overrides, adapted to this repo's compose.yml/dev/prod split and container-naming convention (`erpnext-*` prefix) rather than using their multi-file override system directly.
- Multiple companies are supported under one login (Frappe's own multi-tenancy — separate from the `sites` mechanism, which is for fully separate installs), if you need to track more than one business.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
