# Jellyfin Postgres Test Instance

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Manual-only test instance of Jellyfin running on [JPVenson/Jellyfin.Pgsql](https://github.com/JPVenson/Jellyfin.Pgsql) — a community fork that swaps Jellyfin's SQLite backend for Postgres — to test whether Postgres avoids the SQLite write-contention stalls documented in [`docs/services/jellyfin.md`](jellyfin.md#troubleshooting-streamingsyncplay-hangs-for-1-2-minutes-not-a-scan).
**Port:** `8097` (host) → `8096` (container) | **Data:** `service_data/data/jellyfin-pgsql-test/` | **Requires:** its own Postgres container (`jellyfin-pgsql-test-db`) | **Tier:** `SERVICES_MANUAL` — never started by `up min/core/all`, only via `uv run homeserver.py <env> up jellyfin-pgsql-test`.
**Public URL:** `https://jellyfin-test.${DOMAIN}` (nginx-plain routes it; same-card secondary link on the landing page's Jellyfin card, not its own card).

Completely independent from the real `jellyfin/` service — own container names, own data dir, own Postgres DB. Media is mounted **read-only** from the real jellyfin's library (`service_data/media/jellyfin/`), so nothing here can modify it.

## Setup

```bash
cp jellyfin-pgsql-test/.env.example jellyfin-pgsql-test/.env
# generate a real POSTGRES_PASSWORD: openssl rand -hex 16
uv run homeserver.py dev up jellyfin-pgsql-test
```

First boot seeds an empty Postgres schema via Jellyfin's own EF Core migrations (confirmed: 39 migrations applied cleanly). Add a library pointing at `/media` (read-only) through the normal setup wizard at `https://jellyfin-test.${DOMAIN}` (or `http://<server-ip>:8097` directly) and let it scan — there's no existing data preloaded, see below for why.

## Why the DB is empty, not populated with the real library

This was tested and works — pgloader migration of a real Jellyfin SQLite DB into this fork's Postgres DB succeeded cleanly (71,915 rows across 30+ tables — `BaseItems`, `Users`, `UserData` watch history, `People`, etc. — in ~1.3s). The full procedure, if you want to redo it:

1. Take a **snapshot**, never point anything at the live SQLite file directly: `uv run homeserver.py dev backup jellyfin`, then extract `service_data/backup/jellyfin/<timestamp>/service_data.tar.gz` → `config/data/jellyfin.db`.
2. Stop `jellyfin-pgsql-test` (leave its DB container running) so its schema is seeded but no data has accumulated yet.
3. Run `pgloader` in a throwaway container against a **copy** of the extracted `jellyfin.db`:

   ```bash
   docker run --rm --network homeserver \
     -v "<extracted>/config/data:/data" \
     -v "<repo>/jellyfin-pgsql-test/jellyfindb.load:/jellyfindb.load:ro" \
     dimitri/pgloader:latest pgloader /jellyfindb.load
   ```

   (`jellyfindb.load` control file: `WITH include no drop, truncate, create no tables, create no indexes, reset sequences, quote identifiers` — the `quote identifiers` option is required, without it pgloader downcases identifiers and fails to match EF Core's CamelCase table names against the source, erroring `pgloader failed to find anything in schema "public" in target catalog"`. Mount `/data` **without** `:ro` — SQLite needs to create a journal/WAL file next to the DB even for read-only queries, and a read-only bind mount makes it fail `CANTOPEN`.)
   - One casualty: `KeyframeData` (scrub-preview seek points) fails to migrate — pgloader emits Postgres array literals with `[...]` brackets instead of Postgres's `{...}` syntax, a pgloader casting bug for this column type. Not critical; Jellyfin regenerates it.
   - `__EFMigrationsLock` logs an error ("failed to find target table") — harmless, that table doesn't exist in the Postgres schema at all, only SQLite's.
4. Copy the snapshot's non-DB assets into the test instance's config dir (image/metadata cache, subtitles, collections, playlists) — **not** `config/config/` (server settings) or `config/plugins/` (would clobber the `PostgreSQL` plugin folder this fork needs to boot at all).
5. Restart `jellyfin-pgsql-test`.

**Then it broke on the next restart — this is why the DB was reset back to empty:**

### Confirmed bug: the fork crash-loops on any restart once real data exists

**Symptom:** `Npgsql.PostgresException: 42P07: relation "ActivityLogs" already exists`, fatal, `Main: Error while starting server`, health check reports `Unhealthy... Server is could not complete startup`.

**Root cause:** the plugin (`Jellyfin.Plugin.Pgsql`) has hardcoded, undocumented startup behavior — confirmed by inspecting its DLL for any `POSTGRES_*`-style toggle (none exists beyond the connection env vars in its README). Empirically:

- **First boot** (empty DB, no prior `PgsqlBackups/*.sql` file): takes a defensive backup, no restore attempted, boots fine.
- **Any boot where a `PgsqlBackups/*.sql` file already exists from a previous run**: takes a *fresh* backup of the current (already-populated) DB, then immediately tries to "restore" that same fresh backup back onto itself — and the generated restore SQL has no `DROP`/`IF NOT EXISTS` guards, so every `CREATE TABLE` collides with the table that's already there. Fatal, every time.
- Workaround found empirically: `[INF] Main: Attempt to cleanup JellyfinDb backup.` / `Deleted backup file` — a genuinely clean boot (no leftover backup file at all, e.g. right after `docker compose down` removes the container and its `PgsqlBackups/` dir is cleared) *does* self-clean its own backup file on shutdown-equivalent and boots without the crash. Untested whether this holds up reliably after the instance accumulates its own organic usage data over a longer session — **treat any restart of this fork as a risk**, not confirmed-safe, until proven otherwise across a real multi-day session.

Given this, the migrated data was discarded and the instance was reset to a clean empty DB (`docker compose down` + `docker volume rm jellyfin-pgsql-test_jellyfin-pgsql-test-postgres` + clear `service_data/data/jellyfin-pgsql-test/{config,cache}/` + fresh `up`). This matches the maintainer's own warning: **"NOT meant for a production jellyfin server," "HIGHLY experimental," "use at your own risk."**

## Gotcha: `MEDIA_ROOT` must track the real jellyfin's media location

This instance's `MEDIA_ROOT` points at `service_data/media/jellyfin/` — the real jellyfin's media path *after* the fix documented in `jellyfin.md` (moved out of `service_data/data/jellyfin/` so backups stop sweeping the whole library). If the real jellyfin's media path ever moves again, this `.env` needs updating too, or the library will silently appear empty (confirmed: this exact thing happened once already, mid-development of this instance — the demo's `.env` still pointed at the pre-fix path after the real jellyfin's media had already moved, and the container needs a `--force-recreate` after fixing `.env`, since compose only reads `.env` at container creation, not on every start).

## Fixed: `config/metadata` cache was nested inside `DATA_ROOT`

Same bug and fix as the real jellyfin instance (see `jellyfin.md`'s "Fixed: `config/metadata` cache was also nested inside `DATA_ROOT`" section) — this instance's own scans populate its own separate `config/metadata/` (it doesn't share metadata with the real jellyfin), and it had grown to 1.4GB before being caught. Added `METADATA_ROOT=../service_data/cache/jellyfin-pgsql-test/metadata`, mounted over `/config/metadata` as a second bind mount. Fully regenerable — re-downloads from providers on next scan.

## Migrated: `jellyfin-pgsql-test-db` from `postgres:18.4` to `postgres:18.4-alpine`

Via `uv run homeserver.py dev dump jellyfin-pgsql-test` + `dev migrate jellyfin-pgsql-test` — see `docs/services/forgejo.md`'s "Migrated: forgejo-db..." section for the full process. Clean run, no service-specific gotchas — the fixes already baked into `dump`/`migrate` from migrating forgejo/guacamole/nextcloud first (roles dump/apply before restore, `--clean --if-exists --no-owner` on restore) covered everything here.

## Landing page integration

This instance intentionally does **not** get its own landing-page card. It's a secondary link on the real Jellyfin card (`card-link-secondary`, `data-testsub="jellyfin-test"` in `landing/index.html`), labeled with a small "TEST" badge, resolved to `https://jellyfin-test.${DOMAIN}` by the same `applyDomain()` JS that handles every other card's main link. It does **not** get a live status dot — the landing page's health-check/online-offline-tab-sorting architecture is strictly one-status-per-card, and wiring a second live indicator into that would need real changes to `checkService()`/`placeCard()`, which was out of scope for what's essentially a low-stakes manual test service. A `/health/jellyfin-pgsql-test` route does exist in `landing/nginx.conf`/`landing/nginx.podman.conf` if that's ever revisited.

**Convention going forward:** any future Jellyfin test instance should use the `jellyfin-test` subdomain too (same secondary-link slot), per explicit instruction — don't invent a new subdomain per experiment.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
