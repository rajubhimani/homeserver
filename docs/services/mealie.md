# Mealie

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Recipe manager and meal planner.
**Port:** `9925` (host) → `9000` (container) | **Data:** `service_data/data/mealie/` | **Requires:** Postgres | **Memory:** DB capped 384M in compose.yml; app: no hard limit set; measured idle ~329MB total (app 278 + db 51)

## Setup

```bash
cp services/mealie/.env.example services/mealie/.env
# set POSTGRES_PASSWORD
uv run homeserver.py dev up mealie
```

## Default credentials

`changeme@example.com` / `MyPassword` — **change immediately**.

## Registration

Enabled by default (`ALLOW_SIGNUP=true` in `.env.example`) — set to `false` to close signups once your account exists.

## Using it on Android

There's no official Mealie mobile app — it's PWA-first: open `https://mealie.${DOMAIN}` in Chrome on Android and use the browser menu's **Add to Home Screen** / **Install app** option for a home-screen icon and full-screen view without browser chrome (Mealie's own project has open reports of the install prompt not always appearing — if it doesn't, the site still works fine as a normal bookmarked page). Third-party community apps connecting via Mealie's API also exist (e.g. searchable on GitHub/F-Droid) if a more native feel is wanted, but aren't official and weren't independently verified here.

## Using it day to day

- **Import a recipe by URL:** paste a recipe page's URL and Mealie's built-in scraper extracts name/ingredients/instructions automatically — works on sites using standard `ld+json`/microdata recipe markup (most major recipe sites). Also supports import from a photo or PDF.
- **Meal planning:** drag recipes onto a calendar view to build a weekly plan; a shopping list can be generated from planned meals' combined ingredients.
- **Cookbooks:** group recipes into named collections (e.g. "Weeknight dinners") separate from tags, for browsing rather than searching.

## Health endpoint

No explicit `healthcheck:` on the main `mealie` container in `services/mealie/compose.yml` (only `mealie-db`'s `pg_isready` check exists) — `docker inspect mealie` won't report a health status unless the image bakes in its own, which wasn't confirmed here.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
