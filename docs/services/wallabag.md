# Wallabag

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Read-it-later app — saves a clean, readable copy of articles for offline reading (self-hosted Pocket alternative).
**Port:** `8121` (host) → `80` (container) | **Data:** `service_data/data/wallabag/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~50MB total (app 32 + db 18)

## Setup

```bash
cp services/wallabag/.env.example services/wallabag/.env
# set POSTGRES_PASSWORD and SYMFONY__ENV__SECRET
uv run homeserver.py dev up wallabag
```

**The database schema is not created automatically** — the image doesn't run `wallabag:install` on its own against Postgres. Run it once after the containers are up (the healthcheck will show `unhealthy`/`500` on `/api/info` until this is done):

```bash
docker exec -it wallabag php bin/console wallabag:install --env=prod -n
```

This creates the schema, prompts for (and creates) the admin account, and sets up config defaults. Default credentials if you accept the prompts as-is: `wallabag` / `wallabag` — **change immediately after first login**:

1. Log in at `https://wallabag.<domain>/` with `wallabag` / `wallabag`.
2. Go to **Settings → Password** tab.
3. Set a strong password there and save.

There is no CLI or env-var way to set this directly during install — this
version's console only ships `wallabag:user:list`/`wallabag:user:show`, no
`user:create` or password-reset command (checked via `php bin/console list
wallabag --env=prod` inside the container) — so the web UI's Settings page
is the only supported way to change it, and it should be the first thing
you do after the install step above, before leaving the instance
reachable with the default credentials.

**Running the installer leaves `/api/info` still 500ing afterward**: `docker exec` runs as `root` by default, but the actual request-handling process is `php-fpm`'s `www` pool running as `nobody` (`nginx` serves static assets as its own `nginx` user, unrelated). The installer writes fresh cache files under `var/cache/prod/` as `root`, which `nobody` then can't write to on the next request — surfaces as `The directory ".../jms_serializer_default" is not writable` in `var/logs/prod.log`. Fix once, after running the installer:

```bash
docker exec wallabag chown -R nobody:nobody /var/www/wallabag/var
```

## Connecting the mobile app and browser extension

The web UI alone only gets you the toolbar "+" save box (top nav → **+** icon → paste a URL → Enter). The apps that make wallabag actually useful day to day — saving from your phone or browser without switching tabs — each need to be pointed at `https://wallabag.<domain>` explicitly; installing them does nothing on its own.

**Official mobile apps** — [Android on Google Play](https://play.google.com/store/apps/details?id=fr.gaulupeau.apps.InThePoche) or [F-Droid](https://f-droid.org/en/packages/fr.gaulupeau.apps.InThePoche/); iOS app is on the App Store (search "wallabag"). On first launch, enter:

- **Wallabag address** — `https://wallabag.<domain>` (no trailing slash — the app doc calls this out explicitly)
- **Username** / **Password** — the account created by the installer above

No client ID/secret needed for the official apps — after the connection test passes, they fetch an RSS feed token automatically. Two things that trip this up: the app doesn't support 2FA (disable it on the account first if enabled), and it doesn't always follow HTTPS redirects cleanly, so use the direct `https://` URL rather than anything that redirects.

**Browser extension (Wallabagger)** — [Chrome Web Store](https://chromewebstore.google.com/detail/wallabagger/gbmgphmejlcoihgedabhgjdkcahacjlj) or [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/wallabagger/). Unlike the mobile apps, this one authenticates via OAuth and does need a client ID/secret:

1. In the web UI, go to `https://wallabag.<domain>/developer` (or user menu → **Developer**) → **Create a new client**. Give it any name and redirect URL (not used for this flow) and save — this returns a **Client ID** and **Client secret**, also listed afterward under **Existing clients** on the same page.
2. Right-click the Wallabagger icon → **Options** (or its own settings page). Enter the instance URL, verify it, then paste in the Client ID and secret. The extension refreshes its token automatically after that — no need to touch it again.
3. Click the icon on any page to save it; the popup also lets you tag, star, or archive right from the browser.

**Bookmarklet, for browsers without an extension** — user menu (top right) → **How-to** page → **Add Link** tab → drag the **bag it!** link to your bookmarks bar. Click it on any page to save that URL.

## Registration

`SYMFONY__ENV__FOSUSER_REGISTRATION` in `.env`, default `true`. Set to `false` once accounts exist to close the instance to new signups.

## Notes

- Overlaps in purpose with Karakeep (also in this stack) — Karakeep leans toward bookmark management with AI auto-tagging and full-text search across saved pages, Wallabag leans toward "save this article, strip the clutter, read it later/offline." Both are running because they were chosen deliberately as separate tools, not because one supersedes the other — pick whichever fits a given use case, or drop one later if the overlap turns out not to matter.
- Article content and images live under `service_data/data/wallabag/data/` and `.../images/`.
- Health endpoint: `/api/info`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
