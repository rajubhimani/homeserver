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
# set DB_PASSWORD (MariaDB root password — also used for the one-time
# `bench new-site` command below)

uv run homeserver.py dev up erpnext
```

This brings up 9 containers: `erpnext-db` (MariaDB), `erpnext-redis-cache`, `erpnext-redis-queue`, `erpnext-configurator` (one-shot — writes DB/Redis connection info into the shared `sites` volume, then exits), `erpnext-backend` (Gunicorn), `erpnext-websocket`, `erpnext-queue-short`, `erpnext-queue-long`, `erpnext-scheduler`, and `erpnext` itself (the nginx frontend everything else sits behind — this is the one `nginx-plain` proxies to and the one with the published port).

**First boot only — create the site.** Unlike single-container apps with a web install wizard, Frappe/ERPNext provisions a "site" via a CLI command run once inside the already-running `erpnext-backend` container:

```bash
docker compose -f services/erpnext/compose.yml -f services/erpnext/compose.dev.yml \
  --env-file services/erpnext/.env exec erpnext-backend \
  bench new-site --mariadb-user-host-login-scope=% \
  --db-root-password "$DB_PASSWORD" --install-app erpnext \
  --admin-password <choose-an-admin-password> erpnext.${DOMAIN}
```

Replace `${DOMAIN}` with the actual value from the root `.env`, and pick a real admin password (this is the one you'll actually log in with — it's not read from any `.env` file). This takes a few minutes (installs the ERPNext app's full schema/fixtures into a fresh database). Run it exactly once — running it again for the same site name fails because the site already exists.

**Public hostname (prod):** the Cloudflare tunnel is dashboard-managed, so `erpnext.${DOMAIN}` returns a Cloudflare **502** until you add it: [one.dash.cloudflare.com](https://one.dash.cloudflare.com) → Networks → Tunnels → this tunnel → **Public Hostname** → add `erpnext.${DOMAIN}` → `http://nginx-plain:80` (see [cloudflared's doc](cloudflared.md)). nginx-plain's `erpnext` vhost only takes effect after nginx-plain restarts (`uv run homeserver.py prod up nginx-plain`).

**PDFs:** the default `wkhtmltopdf` generator fetches the page's own CSS over HTTP from the site URL, so until the public hostname above resolves end-to-end it fails with `wkhtmltopdf reported an error: Exit with code 1 due to network error: ConnectionRefusedError`. v16's Chrome generator (`pdf_generator=chrome`, per print format) doesn't have that dependency and works out of the box via the `chromium_path` the configurator sets — verified 2026-09-25 on v16.36.0.

**Setup wizard enables the scheduler:** `bench new-site` ends with `*** Scheduler is disabled ***` — expected; background jobs start once the first-login setup wizard below is completed.

## First login

Browse to `http://<ip>:8153` (dev) or `https://erpnext.${DOMAIN}` (prod, once `nginx-plain`/Cloudflare routing is in place — see [nginx-plain's own doc](nginx-plain.md) if unsure). Log in as `Administrator` with the `--admin-password` chosen above. ERPNext's own setup wizard runs on first login (company name, country, currency, chart of accounts) — this is separate from and after the `bench new-site` step, and only configures the app, not the database.

## Administrator and admin users

**The `Administrator` account is created by `bench new-site`** — its password is whatever `--admin-password` was passed there. It is **not stored anywhere** in this repo or any `.env` (unlike `DB_PASSWORD`), so save it in Vaultwarden straight away. Change it later from the UI: avatar (top right) → **My Settings** → **Change Password**.

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

`services/erpnext/compose.yml`'s healthcheck on the `erpnext` (frontend) container hits `http://localhost:8080/api/method/ping` — this is Frappe's standard unauthenticated liveness endpoint (returns `{"message":"pong"}`), not a generic root-path check.

## Notes

- Image: `frappe/erpnext` — pin the tag in `.env` (`ERPNEXT_VERSION`); check [Docker Hub tags](https://hub.docker.com/r/frappe/erpnext/tags) before bumping, since major-version jumps (`v14` → `v15`) can require running `bench migrate` and reading ERPNext's own release notes first. Pinned to `v16.36.0` (matches upstream `frappe_docker`'s `example.env` as of 2026-09-23). v16 renders PDFs with headless Chromium, so the configurator also sets `chromium_path` (`/usr/bin/chromium-headless-shell`, bundled in the image) — mirrors upstream's `compose.yaml`.
- This stack mirrors the official [frappe_docker](https://github.com/frappe/frappe_docker) production compose + MariaDB/Redis overrides, adapted to this repo's compose.yml/dev/prod split and container-naming convention (`erpnext-*` prefix) rather than using their multi-file override system directly.
- Multiple companies are supported under one login (Frappe's own multi-tenancy — separate from the `sites` mechanism, which is for fully separate installs), if you need to track more than one business.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
