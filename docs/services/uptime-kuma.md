# Uptime Kuma

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Monitor services and alert when something goes down.
**Port:** `3001` (host) → `3001` (container) | **Data:** `service_data/data/uptime-kuma/` | **Requires:** MariaDB (bundled `uptime-kuma-db` container), Docker socket (`${DOCKER_SOCKET}`, read-only — used for Docker Container monitors) | **Memory:** no hard limit set on the app; measured idle ~56MB — `uptime-kuma-db` capped at 384M

## Setup

```bash
cp services/uptime-kuma/.env.example services/uptime-kuma/.env
# edit MYSQL_ROOT_PASSWORD / MYSQL_PASSWORD in .env
uv run homeserver.py dev up uptime-kuma
```

## First login

Browse to `http://<ip>:3001` — create the admin account on first launch, then add monitors for each service subdomain.

## Bulk monitor setup (`setup-monitors.py`)

Adding 30+ monitors by hand through the UI is tedious, so `services/uptime-kuma/setup-monitors.py` automates the initial pass: it lists every currently-running container on the host (`docker ps`), creates a **Docker Container** monitor for each one (excluding `uptime-kuma`/`uptime-kuma-db` themselves — if Uptime Kuma is down it can't alert about itself anyway), adds a `homeserver` Docker host (`unix:///var/run/docker.sock`, matching the read-only socket mount in `compose.yml`), and wires up an `ntfy-homeserver-alerts` notification provider reusing the same ntfy `homeserver-alerts` topic/token the ClamAV watchdog already alerts through (`services/clamav/.env`'s `NTFY_ALERT_TOKEN`, read directly rather than duplicated). Run it with:

```bash
uv run services/uptime-kuma/setup-monitors.py
```

It's a [PEP 723](https://peps.python.org/pep-0723/) inline-metadata script — `uv run` installs its one dependency (`uptime-kuma-api`) into an ephemeral env automatically, nothing to add to the repo's own Python deps. It prompts for your Uptime Kuma username/password interactively (not read from any env file, not persisted anywhere) and is safe to re-run: existing docker host/notification/monitors are matched by name and skipped, so re-running after starting new services only adds monitors for the new ones.

**Docker Container monitor type, not per-service HTTP checks:** this only confirms a container is running (and, if the service's own `compose.yml` defines a `healthcheck`, that Docker considers it healthy) — not that the app inside is actually serving correctly. That's a deliberate scope call for the initial bulk pass, covering "did something crash or fail to start" (the actual `docs`-container-down incident earlier in this stack's history was exactly that — an exit code, which this catches) rather than deeper app-level correctness. Nothing stops adding real `HTTP(s)` monitors by hand later for services where a container being "up" doesn't guarantee the app is actually reachable — the bulk script won't touch or duplicate those, since it only ever looks for its own docker-type monitors by container name.

**Why the script talks to `uptime-kuma-api` with a 30s timeout, not the library's 10s default:** confirmed live against this 2.5.0 pin — a *successful* login's server-side handler (`afterLogin` in `server/server.js`) pushes the entire initial state (monitor list, notification list, docker host list, API key list, status page list, etc.) down the same socket *before* the login ack itself, and over the default long-polling transport that easily exceeds 10s even with only a couple dozen monitors. A *failed* login (bad credentials) responds near-instantly since none of that happens — so this looked at first like the library was flatly broken against 2.5.0 (bad creds worked, good creds timed out) before the real cause (ack ordering, not a protocol break) was found by watching the raw packet trace (`logging.basicConfig(level=logging.DEBUG)` plus setting the same level on `api.sio.logger`/`api.sio.eio.logger`).

**Why not the built-in API Key feature instead of a real login:** Uptime Kuma's own API keys (**Settings → API Keys**) only authenticate the Prometheus `/metrics` endpoint (see Health endpoint section below) — confirmed against `server/server.js`'s socket handlers, there is no REST endpoint for creating monitors or notifications, only the Socket.IO interface the web UI itself uses (what `uptime-kuma-api` wraps, and what this script uses). An API key is the wrong credential for this script even though it looks like the more scoped, less risky choice.

## Using it day to day

There's no client app or agent to install anywhere — Uptime Kuma is purely a web dashboard that reaches out to the things it's watching, not the other way round. Everything below happens in that same web UI (`https://uptime-kuma.${DOMAIN}/` in prod, `http://<ip>:3001` in dev).

- **Adding a monitor:** click **+ Add New Monitor** (top left). Pick a **Monitor Type**, grouped in the dropdown as: General (HTTP(s), HTTP(s) Keyword, TCP Port, Ping, DNS, Docker Container, System Service, PM2 Process, HTTP(s) Browser Engine/Chrome), Passive (Push, Manual — expects something else to call in rather than polling out), Specific (Globalping, gRPC(s) Keyword, HTTP(s) JSON Query, Kafka Producer, MQTT, **NTP** — new in 2.5.0, RabbitMQ, SMTP, SNMP, Websocket Upgrade, and more), Database (Microsoft SQL Server, MongoDB, MySQL/MariaDB, Oracle Database, PostgreSQL, Radius, Redis), and Game Server (GameDig, Steam Game Server) — set a **Friendly Name**, the URL/hostname/port to check, the **Heartbeat Interval** and **Retries** before a monitor flips to down, then save. For every other service in this stack, the natural monitor is HTTP(s) against `https://<service>.${DOMAIN}/`. Verified against this pin's own `src/pages/EditMonitor.vue` source (image `louislam/uptime-kuma:2.5.0`) rather than assumed from a newer version's feature set — the list genuinely grew across releases (e.g. NTP monitoring only shipped in 2.5.0 itself), so don't assume it matches an older or newer pin.
- **Notification channels:** **Settings → Notifications → Set Notification**, configure a channel once, then either check it under a specific monitor's own **Notifications** section, or toggle **Default enabled** on the channel itself so every new monitor gets it automatically with no per-monitor step. This pin ships ~97 built-in providers (confirmed by listing `server/notification-providers/` in the 2.5.0 tag) including Telegram, Discord, Slack, Mattermost, Rocket.Chat, email/SMTP (with custom headers as of 2.5.0), ntfy, Gotify, Pushover, Pushbullet, PagerDuty, Opsgenie, generic Webhook, and Apprise (bridges to 78+ further services Uptime Kuma doesn't implement natively) — plus several 2.5.0-specific additions (Plivo SMS/voice, Ooredoo Maldives SMS, WxPusher, Flowtriq). Verified the provider *list* exists in this pin's source/UI; the `ntfy` provider specifically is wired up for real (see "Bulk monitor setup" above) and a live test alert has been confirmed delivered to ntfy's `homeserver-alerts` topic — the rest of the ~97 remain unconfigured until a specific service actually needs one.
- **Public status pages:** **Status Page → New Status Page** — pick a slug, add one or more groups (e.g. "Infrastructure", "Apps") and drag monitors into them, then publish. The page is served at that slug with no login required to view — hand that link to people who just need to know "is it up," instead of giving them dashboard access.

## Health endpoint

`compose.yml`'s healthcheck is `curl -f http://localhost:3001/` (not the image's own bundled `/app/extra/healthcheck.js`/`.go` script — that one is kept in the image only for backwards compatibility with an old Portainer quirk and is deprecated upstream). Confirmed live via `docker exec uptime-kuma curl -sv http://localhost:3001/`: the root path answers `302 Found` → `Location: /dashboard` (no session yet), which `curl -f` treats as success since it's not a 4xx/5xx — the container reports `healthy` a few checks after startup (`start_period: 30s`, then every 60s).

Uptime Kuma also exposes a Prometheus-format `/metrics` endpoint, gated behind HTTP Basic Auth — confirmed live it currently returns `401 Unauthorized` (`WWW-Authenticate: Basic`) rather than data. There's no separate on/off toggle: before any API key exists it accepts the regular admin username/password over Basic Auth; **Settings → API Keys → Add API Key** generates a dedicated key instead (shown once — save it), and creating the first key permanently disables the admin-password path for this endpoint. Either way, scrape it as `curl -u ":<key-or-password>" https://uptime-kuma.${DOMAIN}/metrics` (empty username, per Uptime Kuma's own wiki) — nothing in this stack scrapes it today, but `observability`'s Prometheus could point at it the same way.

## Database

Uses external MariaDB (`uptime-kuma-db`, own container in this service's compose stack) instead of the app's default bundled SQLite, so monitor/heartbeat data lives in a named Docker volume (`uptime-kuma-mariadb`) and gets picked up automatically by this stack's `backup`/`down` snapshot system — see the `homeserver-backups` skill. Uptime Kuma's default SQLite is the officially recommended choice for a single-instance setup like this one and was already covered by the `service_data/data/uptime-kuma` bind mount; MariaDB was chosen here for consistency with the rest of the stack, not because SQLite had a backup gap. Wired via `UPTIME_KUMA_DB_TYPE=mariadb` and the `UPTIME_KUMA_DB_*` env vars in `compose.yml` (Uptime Kuma ≥2.0 required — this stack runs 2.5.0). Note: Uptime Kuma has no built-in SQLite→MariaDB migration tool — switching `UPTIME_KUMA_DB_TYPE` starts with an empty database.

## Notes

- `TZ` (`.env`, default `Asia/Kolkata`, threaded through `compose.yml`) controls the timezone used for heartbeat timestamps and the status-page clock — same convention as `syncthing`/`firefly`/`audiobookshelf` elsewhere in this stack. Image default without it is UTC.
- `.env.example` documents (commented, image defaults, no behavior change) the rest of Uptime Kuma's server-level env vars worth knowing about: `UPTIME_KUMA_PORT`/`UPTIME_KUMA_HOST` (bind address/port, only useful if you fork the container's internal port off `3001`), `UPTIME_KUMA_DISABLE_FRAME_SAMEORIGIN` (clickjacking protection — leave off unless embedding a status page elsewhere), `UPTIME_KUMA_WS_ORIGIN_CHECK`, `UPTIME_KUMA_ALLOW_ALL_CHROME_EXEC` (browser-engine monitors), `NODE_EXTRA_CA_CERTS` (monitoring an internal HTTPS endpoint signed by a private CA), and `NOTIFICATION_PROXY`. Full list: [Uptime Kuma wiki — Environment Variables](https://github.com/louislam/uptime-kuma/wiki/Environment-Variables).
- Monitor types and notification providers above were verified against the 2.5.0 tag's own source (`src/pages/EditMonitor.vue`, `server/monitor-types/`, `server/notification-providers/`) and its GitHub release notes — not assumed from the latest Uptime Kuma docs, which describe a newer feature set than this pin.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
