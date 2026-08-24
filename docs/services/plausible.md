# Plausible

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted, privacy-friendly web analytics (Google Analytics alternative, no cookies/tracking-consent banner needed).
**Port:** `8130` (host) → `8000` (container) | **Data:** named volumes only (see Notes) | **Requires:** Postgres, ClickHouse | **Memory:** plausible-db capped 384M in compose.yml; app and events-db (ClickHouse): no hard limit set; measured idle ~258MB total across all 3 containers (app 81 + events-db 137 + db 40)

## Setup

```bash
cp services/plausible/.env.example services/plausible/.env
# set POSTGRES_PASSWORD, SECRET_KEY_BASE (openssl rand -base64 64), TOTP_VAULT_KEY (openssl rand -base64 32)
uv run homeserver.py dev up plausible
```

Open `https://plausible.<domain>/` (or `http://<host>:8130` in dev) and create the first account.

## Registration

`DISABLE_REGISTRATION` in `.env`, default `invite_only` (only the first account can self-register; everyone after needs an invite from inside the app — a reasonable closed-by-default posture for a personal instance). Set to `true` to disable entirely, `false` to leave fully open.

## Connecting a site (the tracking snippet)

This is the step that actually gets any data flowing — adding a site in the dashboard alone collects nothing until its snippet is on the actual page. Confirmed against Plausible's own current docs.

1. Main dashboard → **+ Add website** → enter the **Domain**: bare domain, no protocol/`www` (`example.com`, not `https://www.example.com`). A subdomain that needs its own separate stats (e.g. `blog.example.com`) can be added as its own site instead of sharing the parent domain's.
2. Open the new site's menu icon (⋮) → **Settings** → **Tracking** section → **Review** next to "Site installation" — this gives the exact `<script>` tag, pointed at this instance (not `plausible.io`).
3. Paste that snippet into the tracked site's `<head>...</head>`, before the closing tag — on every page you want counted. Most site builders/CMSs have a single "custom head HTML" field for this rather than editing every page by hand.
4. Verify it's working: visit the tracked site yourself, then check **Realtime** (see below) on the Plausible dashboard for that site — a visit should show up within seconds. If nothing appears, it's almost always the snippet pointing at the wrong domain, an ad-blocker on the browser you're testing from, or the snippet not actually deployed to the page you visited.

## Using it day to day

Confirmed against Plausible's own current docs.

- **The stats dashboard** (per site): a top graph of unique visitors / visits / pageviews / bounce rate / visit duration with a date-range picker top-right, then **Sources** (referrers, UTM campaigns), **Top Pages**, **Locations**, **Devices**, and **Goals** below — click any entry in any panel to filter the whole dashboard by it.
- **Realtime:** click the current-visitor count, or pick **Realtime** from the date-range picker, for a live view refreshing every 30s with a 30-minute pageview graph.
- **Goals** (site Settings → Goals → **+ Add goal**): a Pageview goal just needs a path; a custom-event goal needs a matching goal defined here too, or the event arrives but never shows up on the dashboard.
- New accounts after the first need an invite from inside the app (see Registration above).

## Notes

- Three containers: `plausible-db` (Postgres, app metadata), `plausible-events-db` (ClickHouse, the actual analytics event store), `plausible` (the app itself, auto-migrates both databases on every start via `command: sh -c "/entrypoint.sh db createdb && /entrypoint.sh db migrate && /entrypoint.sh run"` — this is the officially documented startup sequence, safe to repeat).
- All persistent data lives in named Docker volumes (`plausible-postgres-alpine`, `plausible-clickhouse-data-alpine`, `plausible-clickhouse-logs-alpine`, `plausible-data`) rather than `service_data/data/` bind mounts — matches this stack's DB-data convention (see the `homeserver-postgres` skill) and upstream's own default. The `-alpine` suffix marks which volumes belong to an Alpine-tagged image (`postgres:18.4-alpine`, `clickhouse-server:26.7.5-alpine`) — a repo-wide naming convention, not Plausible-specific, so switching either image's variant later can't silently orphan the old volume the way `firefly`'s did once.
- `plausible/clickhouse/*.xml` are ClickHouse config overrides taken directly from the upstream `plausible/community-edition` repo: `logs.xml` (quiets ClickHouse's own verbose logging), `ipv4-only.xml` (binds to `0.0.0.0` to avoid an IPv6-listen warning under Docker), `low-resources.xml` + `default-profile-low-resources-overrides.xml` (tuned for <16GB RAM hosts — single-threaded query execution, smaller mark cache).
- Health endpoint: `/api/health`.
- `CLICKHOUSE_USER`/`CLICKHOUSE_PASSWORD` are set explicitly on `plausible-events-db` — the official ClickHouse image **disables network access entirely for the default user** if neither is set (only local/unix-socket access remains), which otherwise surfaces as a confusing `Authentication failed` error from the Plausible app on every connection attempt despite the credentials "looking" unset rather than wrong.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
