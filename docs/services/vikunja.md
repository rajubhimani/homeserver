# Vikunja

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted to-do list and task management app — projects, due dates, labels, Kanban/Gantt views.
**Port:** `8111` (host) → `3456` (container) | **Data:** `service_data/data/vikunja/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~52MB total (app 31 + db 21)

## Setup

```bash
cp services/vikunja/.env.example services/vikunja/.env
# set POSTGRES_PASSWORD and VIKUNJA_SERVICE_SECRET to random values
uv run homeserver.py dev up vikunja
```

Vikunja ships as a single combined image (frontend + API on one port, 3456) as of the 2.x releases — there's no separate frontend/api container to wire up.

## Admin account

No admin account is created on first start. Open `https://vikunja.<domain>/` (or `http://<host>:8111` in dev) and register the first account through the UI — it becomes a regular user, not an auto-promoted admin; grant admin rights from inside the app if needed.

## Registration

`VIKUNJA_ENABLE_REGISTRATION` in `.env` (maps to `VIKUNJA_SERVICE_ENABLEREGISTRATION`) controls self-signup, default `false` (closed). Register your own first account before this matters (see First login above). Vikunja's self-hosted CE has no admin "create user" panel; to add another account later, temporarily set this back to `true`, have them register, then set it back to `false`.

## Connecting the mobile app

Vikunja has official native apps for [Android](https://play.google.com/store/apps/details?id=io.vikunja.app) (Play Store and F-Droid) and [iOS](https://apps.apple.com/us/app/vikunja/id6751271029) that talk to a self-hosted instance — there's no "cloud-only" edition, every install expects you to point it at a server:

1. Install the app from the store above.
2. On the login screen, enter the instance URL: `https://vikunja.${DOMAIN}` (do **not** point it at the bare host/port — the app needs the public HTTPS URL that matches `VIKUNJA_SERVICE_PUBLICURL`, or CORS rejects it).
3. Log in with the account created in the web UI.

This works because `VIKUNJA_SERVICE_PUBLICURL` is already hardcoded to `https://vikunja.${DOMAIN}/` in `compose.yml` (see Notes below) — without a matching public URL, the mobile app's requests get blocked by CORS before login even gets a chance to fail on credentials.

There's also an official CLI ([go-vikunja/app](https://github.com/go-vikunja/app) covers desktop/CLI use) and a full [REST API](https://vikunja.io/docs/api-documentation/) if you want to script task creation instead.

## Using it day to day

- **Projects:** the main organizational unit — create one from the **+** in the sidebar. Projects can be nested (sub-projects) for larger structures.
- **Views:** each project offers List, Kanban (Board), Table, and Gantt views of the same tasks — switch from the tabs at the top of a project; none of them are a separate data set.
- **Tasks:** due dates, priorities, labels, assignees (in shared projects), checklists, and file attachments (capped by `VIKUNJA_FILES_MAXSIZE`, see Notes) all live on the task detail view.
- **Filters and saved filters:** build a reusable query (e.g. "due this week across all projects") and pin it alongside regular projects in the sidebar — useful once there are more than a couple of projects.
- **Labels:** free-form tags, managed from a task's detail view or **Labels** in the sidebar, for cross-project categorization that doesn't fit the project/sub-project hierarchy.

## Notes

- `VIKUNJA_SERVICE_SECRET` signs JWTs — keep it stable across restarts (a rotated value invalidates every existing session). It's set explicitly in `.env` rather than left to the image's random-at-startup default for this reason.
- `VIKUNJA_SERVICE_PUBLICURL` is hardcoded to `https://vikunja.${DOMAIN}/` in `compose.yml` since CORS requires it to match the public-facing URL.
- Health endpoint: `/health` (unauthenticated, returns plaintext `OK`). The container itself is a `scratch`-based image with no shell/curl/wget, so its own `compose.yml` healthcheck uses the binary's built-in `vikunja healthcheck` subcommand instead of an HTTP probe.
- File uploads (task attachments) are capped by `VIKUNJA_FILES_MAXSIZE` (default `20MB`) and stored under `service_data/data/vikunja/files/`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
