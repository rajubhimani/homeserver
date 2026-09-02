# ONLYOFFICE

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Real-time collaborative in-browser editing of Word/Excel/PowerPoint documents stored in [Nextcloud](nextcloud.md), via the standalone ONLYOFFICE Document Server (Community Edition) instead of Nextcloud's built-in CODE (Collabora) editor.
**Port:** `8150` (host) → `80` (container) | **Data:** `service_data/data/onlyoffice/` (`data/`, `log/`, `lib/` — see below) | **Requires:** nothing — self-contained, bundles its own Postgres/RabbitMQ/Redis internally (see "Data paths" below); Nextcloud itself is what depends on this, via its `onlyoffice` connector app | **Memory:** ONLYOFFICE's own docs recommend 2 CPU / 6GB RAM minimum for production workloads; measured idle on this stack, no documents open: **~434MB** — the official figure is a headroom recommendation for heavier concurrent use, not what an idle or lightly-used family instance actually costs.
**Pinned version:** `onlyoffice/documentserver:9.4.0.1`, current stable at the time this was added (confirmed against Docker Hub tags directly, not training-data memory).

## Why a standalone container instead of the built-in CODE server

Nextcloud's **Nextcloud Office** app ships its own built-in CODE (Collabora) server for personal/small-team use out of the box, no extra container needed. That's fine at low load, but gets noticeably slower once more than one or two people are co-editing the same document at once — this container replaces that bottleneck with a dedicated, full-scale Document Server.

**ONLYOFFICE vs. Collabora, decided here:** ONLYOFFICE was chosen over a standalone Collabora container because it renders `.docx`/`.xlsx`/`.pptx` more faithfully (native OOXML engine, vs. Collabora's LibreOffice/ODF-based engine) — better fit for a household working mostly with Microsoft-format files. The Community Edition's 20-concurrent-document cap (a business-model limit on the official image, not a technical one) is irrelevant at family scale.

**Running both editors side by side was deliberately avoided** — Nextcloud lets you install both the `richdocuments` (Collabora) and `onlyoffice` apps at once and assign a default handler per file type, but real-world reports describe the two apps fighting over the same mimetypes (one re-registering itself as the handler Nextcloud opens files with, regardless of the configured association). Switching from ONLYOFFICE to Collabora later, if ever needed, is cheap and safe regardless: documents are always stored as plain `.docx`/`.xlsx`/`.pptx`/`.odt` files, never in an editor-specific format, so there's no migration step beyond disabling one app and enabling/configuring the other.

## Setup

```bash
cp services/onlyoffice/.env.example services/onlyoffice/.env
# JWT_SECRET is already generated in .env if you're reading this after the
# initial setup pass — otherwise generate one: openssl rand -hex 32
uv run homeserver.py dev up onlyoffice
```

Then in Nextcloud:

```text
Apps → search "ONLYOFFICE" → Enable
Settings → Administration → ONLYOFFICE
  ONLYOFFICE Docs address: https://onlyoffice.${DOMAIN}/
  Secret key (JWT): <same value as JWT_SECRET in services/onlyoffice/.env>
  → Save → the page runs a live connection test automatically
```

Confirmed working end-to-end on this instance — connection test passes with exactly those two fields, nothing else required to get a green status.

**Advanced server settings (recommended):** the same admin page has an "Advanced server settings" section for internal addresses — set **ONLYOFFICE Docs address for internal requests from the server** to `http://onlyoffice/` (the container name, resolved over the internal `homeserver` Docker network) instead of the public `https://onlyoffice.${DOMAIN}/`. Without this, Nextcloud's server-to-server calls to the Document Server leave the host through `cloudflared`, round-trip Cloudflare, and come back in — a needless hairpin that also depends on the tunnel being up for two containers on the same Docker network to talk to each other. Leave the **returning Nextcloud address for internal requests from ONLYOFFICE Docs** field as the public `https://nextcloud.${DOMAIN}/` — the Document Server needs to reach Nextcloud the same way a real browser would, since it fetches/saves document content over that URL via WOPI-style calls, and Nextcloud validates the request's origin against `trusted_domains`.

## What `onlyoffice.${DOMAIN}` actually is — don't visit it directly

Unlike every other service in this stack, this subdomain isn't a destination app — there's no login page, no file browser, no "your documents" list. It's a backend rendering/editing engine that Nextcloud's `onlyoffice` app calls into behind the scenes: open a file in Nextcloud's **Files** app, and the editor is silently loaded from this container inside the same page — you'd only ever see the domain itself if you inspected the browser's network tab. The only things a real visit to `https://onlyoffice.${DOMAIN}/` shows are `/welcome/` (a bare "server is running" placeholder) and `/healthcheck` (used by the landing-page status dot). Same relationship as `guacd` is to Guacamole, or the ML container is to Immich — a worker process, not a front door. Day-to-day, family members should only ever go to `nextcloud.${DOMAIN}` and open/create files there normally.

## Using it day to day

Confirmed against ONLYOFFICE's and Nextcloud's own current documentation, not assumed from memory.

- **Opening an existing file:** in Nextcloud's **Files** app, click any `.docx`/`.xlsx`/`.pptx`/`.odt`/`.ods`/`.odp` file — it opens directly in an in-browser editor instead of downloading. No separate ONLYOFFICE login; it inherits your Nextcloud session.
- **Creating a new one:** **Files → + New → Document / Spreadsheet / Presentation** creates a blank file and opens the editor immediately.
- **Real-time co-editing:** if a second logged-in family member opens the same file, both editors show each other's cursor and changes live, same as Google Docs — no "locked by another user" message, no manual merge.
- **Saving:** autosaves continuously while editing; closing the editor (or the browser tab) finalizes it as a new version of the file. Nextcloud's own version history (right-click the file → **Details** → **Versions**) captures these like any other edit, so past versions are recoverable the normal Nextcloud way.
- **Desktop/sync clients:** editing always happens through the browser-based editor — the desktop sync client and mobile auto-upload just sync the resulting file like any other, they don't open the ONLYOFFICE editor themselves.
- **Mobile:** works the same way through a mobile browser (open Nextcloud's web UI, tap the file). The official Nextcloud mobile app's in-app editing support for this has had inconsistent user reports, so a mobile browser tab is the dependable path if the in-app version misbehaves.

## Looking ahead: Euro-Office

Nextcloud itself now ships a competing option, **Euro-Office** (launched June 2026) — a fork of ONLYOFFICE's own open-source engine that Nextcloud maintains directly, with no concurrent-document cap at all. It was evaluated when this service was added and deliberately not chosen yet: real self-hosters report it works on a traditional (non-AIO) setup like this stack's, but its Nextcloud connector app had **74 open GitHub issues** at the time of evaluation (locale bugs, a document-unlock bug, minor UI glitches) consistent with a project that's ~3 months old. Worth re-evaluating in 6–12 months once it's had more time to stabilize — switching later costs nothing beyond the setup time, since documents are stored in plain, editor-agnostic formats regardless of which engine touches them.

## JWT secret

`JWT_SECRET` (`services/onlyoffice/.env`) authenticates every request between Nextcloud and this container — without it, anyone who can reach `onlyoffice.${DOMAIN}` could open/edit documents directly. It must be entered **verbatim** as the "Secret key" in Nextcloud's ONLYOFFICE admin page above; a mismatch fails with a JWT/token error on the connection test, not a helpful "wrong secret" message. `.env.example` documents `openssl rand -hex 32` as the generation command — the version already in `.env` was generated the same way when this service was added.

## The bundled `/example/` demo editor

The image ships its own standalone demo/sandbox editor at `/example/` (own isolated storage, no relation to Nextcloud or real files) — useful only for testing the Document Server in isolation, never part of the real Nextcloud integration. Two things worth knowing:

- **`EXAMPLE_ENABLED=true`** (`.env`) turns on its backing process (`ds:example` in `docker exec onlyoffice supervisorctl status` — `autostart=false` in the image by default, so it's `STOPPED` unless this is set). Set to `false` to disable the process entirely.
- **Deliberately blocked on the public route** — `services/nginx-plain/templates/default.conf.template`'s `onlyoffice.${DOMAIN}` block returns `404` on `location /example/` before falling through to the normal proxy. The demo page has no login of its own, so leaving it reachable from the public internet would let anyone use the server's CPU for free; blocking just this one path costs nothing since Nextcloud never calls it. Still reachable internally on the dev port (`http://127.0.0.1:8150/example/`) for admin testing.
- **A `500` there isn't a real problem either way** — even with `EXAMPLE_ENABLED=true` and the process running, the demo app throws its own internal `fetch failed` error hitting its own backend on this stack (not investigated further, since it has zero effect on the actual editing integration — `docservice`/`converter`, the two processes Nextcloud's connector talks to, stay `RUNNING` and unaffected regardless of `/example/`'s state).

## Health endpoint

`compose.yml`'s healthcheck hits `http://localhost/healthcheck` inside the container every 30s (10s timeout, 5 retries, 90s start period) — the documented ONLYOFFICE endpoint, returns the plain-text body `true` on success. `services/landing/nginx.conf`'s `/health/onlyoffice` route proxies to the same path for the landing-page card.

## Data paths

Three bind-mounted subdirectories under `DATA_ROOT` (`service_data/data/onlyoffice/`), matching ONLYOFFICE's own documented Docker volume layout:

- `data/` → `/var/www/onlyoffice/Data` — server certificates/keys used internally by the Document Server.
- `log/` → `/var/log/onlyoffice` — application logs.
- `lib/` → `/var/lib/onlyoffice` — converted-file cache.

No database — unlike most services in this stack, the Community Edition documentserver image bundles its own internal Postgres/RabbitMQ/Redis inside the single container rather than needing sibling containers, so there's nothing else in `compose.yml` beyond the one `onlyoffice` service.

## Reverse proxy notes

`services/nginx-plain/templates/default.conf.template`'s `onlyoffice.${DOMAIN}` block proxies WebSocket traffic (`proxy_http_version 1.1` + conditional `Connection: upgrade`, same pattern as Guacamole) since real-time co-editing runs over a WebSocket connection, plus a raised `client_max_body_size 100M` and `proxy_read_timeout 600s` for large document uploads/format conversions.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
