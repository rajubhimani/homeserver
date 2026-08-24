# HomeBox

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted home inventory tracker — log items (pendrives, cables, tools, anything in a box/drawer/closet) under locations and labels, print QR codes for boxes, then scan with your phone to pull up what's inside.
**Port:** `8136` (host) → `7745` (container) | **Data:** `service_data/data/homebox/` | **Requires:** nothing (bundled SQLite) | **Memory:** no hard limit set; measured idle ~26MB

Maintained fork: [`sysadminsmedia/homebox`](https://github.com/sysadminsmedia/homebox) — the original `hay-kot/homebox` repo was archived in June 2024. Image: `ghcr.io/sysadminsmedia/homebox:0.26.2`, pinned — check [releases](https://github.com/sysadminsmedia/homebox/releases) for updates.

## Setup

```bash
cp services/homebox/.env.example services/homebox/.env
# Replace HBOX_AUTH_API_KEY_PEPPER with a real secret (must be >= 32 bytes):
#   openssl rand -base64 48
uv run homeserver.py dev up homebox
```

Open `https://homebox.<domain>/`, register the first (and only) account, then set `HBOX_OPTIONS_ALLOW_REGISTRATION=false` in `.env` and restart to lock out further signups — see "Registration / access model" below.

## Usage model

- Create a **Location** (e.g. "Closet", "Garage Shelf") and, if useful, nested sub-locations (e.g. "Closet → Drawer 2").
- Add **Items** under a location — name, quantity, photo, purchase info, warranty. Attach **Labels** (e.g. "cables", "electronics") to cut across the location tree when searching.
- Print a QR code per location or item (Inventory → Label Maker) and stick it on the physical box/drawer. Scanning it with a phone camera opens that location/item directly — no native app exists (nor an official PWA manifest to install one), it's just a normal responsive web page that works fine in any mobile browser. Bookmarking `https://homebox.${DOMAIN}/` (or your phone's "Add to Home Screen" from the browser's own share/menu, which works on any site, not something HomeBox-specific) is the closest thing to an app icon.
- Barcode lookups (BarcodeSpider / Open Food Facts / Open Beauty Facts / Open Products Facts) can auto-fill an item's name/photo from a scanned product barcode if `HBOX_BARCODE_TOKEN_BARCODESPIDER` or `HBOX_BARCODE_OPEN_FOOD_FACTS_CONTACT` are set in `.env` — optional, unset by default.

## Registration / access model

`HBOX_OPTIONS_ALLOW_REGISTRATION=true` by default (image default), matching this stack's "toggle defaults to enabled" convention. Since this is a personal single-user inventory exposed at a public subdomain, create your own account right after first start, then set it to `false` and restart — there is no invite-only/admin-approval middle ground in HomeBox itself.

## Notes

- **Required secret:** `HBOX_AUTH_API_KEY_PEPPER` — HMAC pepper for stored API key hashes. The binary refuses to start if it's shorter than 32 bytes. Generate with `openssl rand -base64 48` and never rotate it casually — rotating invalidates every issued API key.
- **Reverse proxy:** `HBOX_OPTIONS_TRUST_PROXY` is hardcoded to `"true"` in `compose.yml` (not exposed via `.env`) — HomeBox needs this to read `X-Forwarded-Proto`/`X-Forwarded-For` correctly behind nginx-plain; without it, label generation and IP-based rate limiting misbehave. The nginx-plain route also sets `proxy_http_version 1.1` + `Upgrade`/`Connection` headers and a 24h `proxy_read_timeout`, because the web UI holds a long-lived WebSocket open to `/api/v1/ws/events`.
- **Storage/database paths are intentionally not touched:** `HBOX_STORAGE_CONN_STRING`, `HBOX_STORAGE_PREFIX_PATH`, and `HBOX_DATABASE_SQLITE_PATH` are all hardcoded in the upstream Docker image to point at `/data` — upstream docs explicitly say not to override these under Docker. All items, attachments, and the SQLite DB live under `service_data/data/homebox/data/`.
- **Health check:** `/api/v1/status` (the same endpoint the upstream image's own `HEALTHCHECK` uses) — wired into both `compose.yml`'s healthcheck and the landing page's `/health/homebox` route.
- **Not wired up:** OIDC login (`HBOX_OIDC_*`, e.g. against Authentik) and outbound email (`HBOX_MAILER_*`, needed for password-reset emails) are both left at their off/unset defaults — single-user personal deployment doesn't need either. See `services/homebox/.env.example`'s "Remaining env vars" block if you want to enable them later.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
