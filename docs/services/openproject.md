# OpenProject

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Project management with Gantt charts, wikis, and issue tracking.
**Port:** `8099` (host) → `80` (container) | **Data:** `service_data/data/openproject/` | **Requires:** 4096MB (4GB) stated minimum per OpenProject's own docs, bundled Postgres — corrected from a previous, lower unverified figure in this doc

## Setup

```bash
cp services/openproject/.env.example services/openproject/.env
# generate: openssl rand -hex 64 → SECRET_KEY_BASE
uv run homeserver.py dev up openproject
```

## Default login

`admin` / `admin` — **change immediately** on first login.

To set a real name/email/password from the start instead (fresh installs
only — see `.env.example`'s commented `OPENPROJECT_SEED_ADMIN_USER_*`
block), fill those in **before** the first `up openproject`. They're seed
vars: only read during the initial `db:seeds` run that creates the
database, so setting them on an already-running instance has no effect —
change the password via the UI instead (Administration → Users, or your
own account settings). Note there's no seed var for the *login* itself —
OpenProject hardcodes it to `admin` regardless of what
`OPENPROJECT_SEED_ADMIN_USER_NAME`/`_MAIL` are set to.

**However you get in — default `admin`/`admin`, or a seeded password —
`OPENPROJECT_SEED_ADMIN_USER_PASSWORD_RESET` defaults to `true`, so
OpenProject forces a password change screen on first login either way.**
Setting it to `false` in `.env` (fresh installs only, same caveat as
above) skips that prompt and lets the seeded password be used as-is.

## Implementation note — HTTPS behind Cloudflare

`OPENPROJECT_HTTPS` must be `"true"` when running behind Cloudflare/any TLS-terminating proxy. This is OpenProject's own documented env var for telling Rails the connection is secure, independent of the `X-Forwarded-Proto` header the proxy sends. Leaving it `"false"` while the proxy claims `https` is contradictory and causes broken links/redirect issues.

## Implementation note — bundled Postgres

The single `openproject` container runs its own internal Postgres rather than using a separate `openproject-db` container like most other services in this stack. Its data lives in the named volume `openproject-pgdata` (`/var/openproject/pgdata`), which already follows the same named-volume-not-bind-mount rule as a standalone DB container, for the same reason (see the `homeserver-postgres` skill).

**Memory cap:** `deploy.resources.limits.memory: 3G` — **this is already below OpenProject's own stated 4GB minimum** (see top of doc, openproject.org/docs/installation-and-operations/system-requirements/). It's a backstop cap rather than internal Postgres tuning (the bundled Postgres isn't separately configurable the way a standalone `<service>-db` container's `command:` flags would be). **Measured idle usage is already 1.94GB (65% of the 3G cap) with zero users** — real risk of OOM-kill under actual multi-user load. Raise the cap to at least 4G if that happens; recreate just this container after changing it: `docker compose -f compose.yml -f compose.prod.yml up -d --no-deps openproject`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
