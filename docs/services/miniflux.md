# Miniflux

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Minimal, fast RSS reader with keyboard shortcuts, no JavaScript frontend.
**Port:** `8093` (host) → `8080` (container) | **Data:** `service_data/data/miniflux/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~29MB total (app 13 + db 16)

## Setup

```bash
cp services/miniflux/.env.example services/miniflux/.env
# set MINIFLUX_ADMIN_USER, MINIFLUX_ADMIN_PASSWORD, POSTGRES_PASSWORD
uv run homeserver.py dev up miniflux
```

## Admin account

Created on first start from `MINIFLUX_ADMIN_USER` / `MINIFLUX_ADMIN_PASSWORD` in `.env`.

## Connecting a client app

Most people don't live in Miniflux's web UI day to day — they read through a dedicated mobile/desktop client that syncs against Miniflux's API in the background. Point any client at this instance and authenticate with an **API key** rather than handing out the admin password (per-app, independently revocable, and it's what Miniflux's own docs recommend over basic auth):

1. Log into the web UI (`https://miniflux.${DOMAIN}/`) → **Settings → API Keys → Create a new API key**. Name it after the client, e.g. "Phone - Fleuron".
2. In the client app's add-account screen, enter:
   - **Server URL:** `https://miniflux.${DOMAIN}`
   - **API key:** the value from step 1 — most Miniflux-aware clients have a dedicated "API Key" field; a few instead ask for username + password with the key pasted in as the password.

Clients confirmed against Miniflux by its own [Third-Party Applications](https://miniflux.app/docs/apps.html) list:

- **Android:** Fleuron (Material You, built specifically for Miniflux), Capy Reader, Read You, FeedMe, Microflux, Miniflutt
- **iOS/macOS:** FluxNews, Reeder Classic, Unread, ReadKit
- **Desktop/cross-platform:** Fluent Reader, NewsFlash (Linux), Newsboat (terminal)

Miniflux also implements the Fever and Google Reader APIs, so older readers that don't know about Miniflux natively (only Fever/Reader-compatible mode) still work against the same server and credentials.

## Using it day to day

Everything below is in the web UI, but the same concepts (categories, filter rules) apply no matter which client you actually read through, since they're server-side.

- **Adding a feed:** the **+** / "Add subscription" link → paste a site or feed URL. Miniflux auto-discovers the actual feed URL from a regular web page in most cases, no need to find the raw `/feed` link yourself.
- **Categories:** group feeds into folders — assign one when adding/editing a feed, or manage the list from the Categories page. Drives the sidebar grouping and lets you filter the unread list by category.
- **Filter rules (Block/Keep):** per-feed regex rules under that feed's **Edit** page, or global ones on the **Settings** page — a **Block rule** hides any entry whose title/content/URL matches the regex, a **Keep rule** does the opposite (only entries matching the regex are kept). Useful for noisy feeds with a few recurring off-topic posts. Full syntax: [Filter, Rewrite, and Scraper Rules](https://miniflux.app/docs/rules.html).
- **Keyboard shortcuts:** Miniflux is built around them (no heavy JS UI) — `j`/`k` to move between entries, `o` to open, `m` to toggle read/unread, `s` to star. Full list is in-app under **Settings → Keyboard Shortcuts**.

## Notes

- Health endpoint: `/healthcheck`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
