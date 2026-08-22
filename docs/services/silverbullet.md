# SilverBullet

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Markdown notes with a query language over your own space — lightweight, no plugin sprawl.
**Port:** `8113` (host) → `3000` (container) | **Data:** `service_data/data/silverbullet/` | **Requires:** nothing (plain markdown files on disk, no DB) | **Memory:** no hard limit set; measured idle ~2MB

## Setup

```bash
cp services/silverbullet/.env.example services/silverbullet/.env
# set SB_USER to username:password
uv run homeserver.py dev up silverbullet
```

Open `https://silverbullet.<domain>/` (or `http://<host>:8113` in dev) and log in with the `SB_USER` credentials.

## Registration

None — single space, single basic-auth login set via `SB_USER` in `.env` (format `username:password`). No public signup exists to toggle.

## Installing it as an app (PWA)

SilverBullet is a Progressive Web App — installing it once makes it behave like a native app (own window/icon, works fully offline against a local IndexedDB copy of your space, syncs back once reconnected):

- **Desktop (Chrome/Edge):** click the install icon in the address bar, or browser menu → "Install SilverBullet."
- **iOS (Safari):** Share button → **Add to Home Screen**.
- **Android (Chrome):** browser menu → **Add to Home Screen** / **Install app**.

Either way, log in with the same `SB_USER` credentials — the installed app is just a chrome-less wrapper around the same login-gated page, not a separate account or a second space.

## Using it day to day

- Pages are plain markdown; `[[Wiki-style links]]` create/navigate between pages, and `#tags` anywhere in a page make it queryable.
- **Command Palette** (`Ctrl+/` / `Cmd+/`) is the fastest route to any action — page creation, search, settings — from anywhere in the app.
- **Query blocks** (fenced ` ```query ` blocks) are the differentiator vs. a plain markdown folder — e.g. a live-updating table of every page tagged `#project`. See SilverBullet's own [Manual](https://silverbullet.md/Manual) for query syntax once running.
- Full-text search across the whole space via the Page Picker's search mode.

## Notes

- Notes are plain markdown files under `service_data/data/silverbullet/space/` — greppable, syncable, versionable like any other file tree.
- Health endpoint: `/.ping` — returns HTTP 200 with an empty body when the server is up; the compose healthcheck just checks for a successful `curl --fail`.
- The Runtime API (headless-Chrome integration for things like link-preview screenshots) auto-enables itself only if Chrome/Chromium is present in the image — this image doesn't bundle one, so it's off by default; `SB_RUNTIME_API`/`SB_CHROME_PATH`/`SB_CHROME_DATA_DIR` in `.env.example`'s remaining-vars block would only matter if a Chrome binary were ever added to a custom image.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
