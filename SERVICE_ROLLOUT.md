# Service rollout tracker

Scratch tracking doc for bringing up `SERVICES_EXTRA` in batches (10 at a time, picked by lowest container count / setup complexity first). Not a permanent doc — delete once everything's running, or fold into `docs/11-services-reference.md` if it's worth keeping.

Check current live status any time with:

```bash
python3 homeserver.py status
```

## Already running before batching started

MIN + CORE tiers, all 5 browsers, and `stirling-pdf` (manual tier, started on request).

## Batch 1

dozzle, dockge, uptime-kuma, stirling-pdf-lite, audiobookshelf, trilium, silverbullet, excalidraw, ntfy, homebox

**Status:** ✅ all running at some point, ✅ user-tested and confirmed good. `dozzle` and `excalidraw` are stateless (no volumes/data dir) and have since been stopped again — offline is expected, not broken.

## Batch 2

mailpit, adguard-home, open-webui, mealie, syncthing, miniflux, invoiceshelf, vikunja, nocodb, atuin

**Status:** ✅ all running, ✅ user-tested and confirmed good. Notable fixes applied along the way:

- `adguard-home` — port 53 conflicted with `systemd-resolved`; bound to LAN IP via `DNS_BIND_IP` instead of `0.0.0.0`.
- `invoiceshelf` — required pre-created `storage/` subdirectories (documented gotcha); later hit `AUTORUN_LARAVEL_MIGRATION` racing the install wizard, fixed permanently in `.env`.
- `stirling-pdf` (full, manual) — enabled login (`SECURITY_ENABLELOGIN`); `stirling-pdf-lite` can't support login at all (ultra-lite image has no security module).
- `atuin` — client `sync_address` config gotcha, documented in `docs/services/atuin.md`.

## Batch 3

ollama, crowdsec, bookstack, mattermost, n8n, wallabag, orangehrm, listmonk, documenso, calcom

**Status:** ✅ all running at some point, ✅ tested and confirmed good. `ollama`, `crowdsec`, `mattermost`, `n8n` are currently up; `bookstack`, `wallabag`, `orangehrm`, `listmonk`, `documenso`, `calcom` were each individually brought up, fixed where needed, verified, and then stopped (`down`, auto-backed up) once confirmed — currently offline, not because anything's wrong. Notable fixes applied along the way:

- `ollama` — plain `up ollama` silently no-ops (`no service selected`) — it's gated behind the `docker-ollama` compose profile (see `docs/services/open-webui.md`, kept deliberately for a future host-native-GPU option). Always start it with `uv run homeserver.py dev up ollama --profile docker-ollama`.
- `wallabag` — image doesn't auto-create its DB schema (documented in `docs/services/wallabag.md`); needed `docker exec wallabag php bin/console wallabag:install --env=prod -n` once. That command itself left cache files root-owned (it runs as `root` via `docker exec`, but php-fpm serves as `nobody`), which had to be fixed with `docker exec wallabag chown -R nobody:nobody /var/www/wallabag/var` — also now documented. Default admin (`wallabag`/`wallabag`) password-change steps (Settings → Password) documented too, since there's no CLI/env-var way to set it directly.
- `orangehrm` — official image has no confirmed env-var DB wiring (web installer only); its own compatibility check requires MariaDB `>5, <12`, so it needed pinning to `mariadb:11.4` instead of the stack-wide `12.3.2` default. Web installer's "Existing Empty Database" fields documented in `docs/services/orangehrm.md`.
- `outline` — OIDC login was broken: `.env` still had the literal placeholder `OIDC_CLIENT_ID`/`OIDC_AUTH_URI` (pointing at `authentik.yourdomain.com`) from `.env.example`, never actually filled in. Authentik provider/application created, real credentials set, and the three OIDC URLs moved into `compose.yml` as `${DOMAIN}`-derived values so they auto-track the root `.env`'s `DOMAIN` instead of needing manual edits. Full Authentik setup walkthrough documented in `docs/services/outline.md`.

## Batch 4

openproject, paperless, authentik, appflowy, plane, outline, karakeep, rocketchat, zulip, airflow, temporal, dagster, penpot, coolify, supabase, observability

**Status:** mixed — see breakdown below. `outline` also appears here (OIDC fix landed while working through this batch) as well as in Batch 3's fix notes above.

- ✅ **Running now:** `authentik`, `plane`, `zulip`, `coolify`, `observability` — all confirmed good. `coolify` had `postgres` (`18.4-alpine → 18.6-alpine`) and `coolify-realtime` (`1.0.16 → 1.0.17`) bumped to real available updates; the main `coolify` image switched off `:edge` onto the real pinned tag `4.3.9` — real semver tags did exist on Docker Hub the whole time, the earlier "no stable release" conclusion came from checking Docker Hub's recency-sorted tag list instead of searching by tag name. Also fixed `coolify-proxy` (Coolify's own Traefik, separate from `nginx-plain`) getting stuck on "starting" forever — its default config wanted host port `8080`, already owned by `landing`; dropped the optional Traefik dashboard to resolve it. Documented both, plus a "never use Coolify's in-app Upgrade button" gotcha (it forks Coolify onto its own separately-managed compose files), in `docs/services/coolify.md`.
- ✅ **Tested and confirmed good, currently offline** (stopped after testing, not broken): `paperless`, `appflowy`, `outline`, `rocketchat` (image bump to `8.7.0` + Mailpit SMTP wiring, brought up and back down clean), `supabase` (Mailpit SMTP wiring fixed in `.env.example`, Studio dashboard Basic Auth credentials confirmed set; brought down after use — not yet browser-verified end to end), `airflow`, `temporal`, `dagster` (self-seeding Docker image fix confirmed — auto-copies `worker.py`/`definitions.py`/example DAGs into the bind-mounted data dir on first empty start — see `docs/services/temporal/temporal.md`, `docs/services/dagster/dagster.md`, `docs/services/airflow/airflow.md`), `penpot`, `openproject` (image bump to `17.7.2` + Mailpit SMTP wiring; admin account reseeded from a clean `openproject-pgdata` volume with real name/email/random password via `OPENPROJECT_SEED_ADMIN_USER_*`, forced password-change confirmed working on first login), `karakeep` (Bucket C — real accounts, no admin/role tiering; `karakeep-chrome`'s image was failing to pull — `gcr.io/zenika-hub/alpine-chrome:124` started requiring GCP billing, an upstream GCR change — switched to `ghcr.io/karakeep-app/karakeep-chrome:release`, Karakeep's own maintained image; also bumped `meilisearch` to `v1.53.1` and wired Mailpit SMTP).
- ⬜ **Not yet started at all:** none — every Batch 4 service has been attempted at least once now.
- ⚠️ **`gitlab` — needs a fix before next start, not just a re-up.** Was running with an uncommitted image bump (`19.2.1-ce.0 → 19.2.4-ce.0`) plus new Mailpit SMTP config (still uncommitted in `services/gitlab/compose.yml`). A `gitlab-ctl reconfigure` at 15:02 restarted its internal services under the container's `memory: 6G` cap; ~18 minutes later the kernel started OOM-killing GitLab's `ruby` workers (Puma/Sidekiq) inside that cgroup, and it never stopped — **1,579 kills over 5 hours**, GitLab endlessly respawning workers that got killed again immediately. The host itself hung (black screen) and needed a hard power-off — journald's log for that boot just stops mid-crash-dump, no clean shutdown ever recorded. Confirmed healthy again after reboot, then intentionally stopped. Root cause (6G is too tight for GitLab CE, especially right after an upgrade) is **not yet fixed** — raise the memory limit in `compose.yml` before starting it again.

## Also confirmed good (outside the batch numbering)

- `plausible` — nginx-plain was missing WebSocket upgrade headers on its proxy block, which silently hung the LiveView-based "Create my account" flow (fixed, `docs/services/plausible.md`/`services/nginx-plain/templates/default.conf.template`). Tracking sites added for `www.${DOMAIN}` and `docs.${DOMAIN}`.
- `mailpit` — this stack's SMTP test-catcher, used by nearly every other service's Mailpit-wiring fix above.

Both `plausible` and `mailpit` were moved from `SERVICES_EXTRA` into `SERVICES_MIN` (always-on infra tier) once confirmed good — see `CLAUDE.md`'s tier list. `stirling-pdf` (full) was also moved out of `SERVICES_MANUAL` into `SERVICES_EXTRA` (image bump to `2.14.3` picked up, confirmed working) — only `gitlab` remains in `SERVICES_MANUAL` now.
