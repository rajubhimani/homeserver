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

- `ollama` — plain `up ollama` silently no-ops (`no service selected`) — it's gated behind the `docker-ollama` compose profile (see `docs/services/open-webui.md`, kept deliberately for a future host-native-GPU option). Always start it with `uv run homeserver.py dev up ollama --profile docker-ollama`. Also: `homeserver.py`'s `do_update()` hardcodes `profile=None` when calling compose up, so `dev update ollama` fails the same "no service selected" way even with `--profile` on the command line — `dev up`/`dev restart` do pass it through correctly, so a version bump on a profile-gated service needs `docker pull` + `up --profile <name>` instead of `update`, not a bug in the flag itself.
- **`ollama` + `open-webui` re-tested end to end** (fresh containers, `ollama` bumped `0.32.14 → 0.32.15`): found and fixed a real gotcha — `OLLAMA_BASE_URL` in `services/open-webui/.env` only seeds Open WebUI's `ollama.base_urls` config on a first boot against an *empty* `webui.db`; once that DB exists (this stack's did, from the original Batch 2 bring-up), every later boot reads the persisted DB value instead, so editing `.env` alone to switch from host-native to containerized Ollama silently does nothing — has to also be changed in Admin Panel → Settings → Connections. Documented in `docs/services/open-webui.md`'s Gotchas. Also confirmed models can be pulled entirely from the Open WebUI UI (Admin Panel/Workspace → Models → pull by name) with zero `ollama`/`docker exec` CLI access needed — also now documented. Both moved from `SERVICES_EXTRA` to `SERVICES_DAILY` after this pass.
- `wallabag` — image doesn't auto-create its DB schema (documented in `docs/services/wallabag.md`); needed `docker exec wallabag php bin/console wallabag:install --env=prod -n` once. That command itself left cache files root-owned (it runs as `root` via `docker exec`, but php-fpm serves as `nobody`), which had to be fixed with `docker exec wallabag chown -R nobody:nobody /var/www/wallabag/var` — also now documented. Default admin (`wallabag`/`wallabag`) password-change steps (Settings → Password) documented too, since there's no CLI/env-var way to set it directly.
- `orangehrm` — official image has no confirmed env-var DB wiring (web installer only); its own compatibility check requires MariaDB `>5, <12`, so it needed pinning to `mariadb:11.4` instead of the stack-wide `12.3.2` default. Web installer's "Existing Empty Database" fields documented in `docs/services/orangehrm.md`.
- `outline` — OIDC login was broken: `.env` still had the literal placeholder `OIDC_CLIENT_ID`/`OIDC_AUTH_URI` (pointing at `authentik.yourdomain.com`) from `.env.example`, never actually filled in. Authentik provider/application created, real credentials set, and the three OIDC URLs moved into `compose.yml` as `${DOMAIN}`-derived values so they auto-track the root `.env`'s `DOMAIN` instead of needing manual edits. Full Authentik setup walkthrough documented in `docs/services/outline.md`.

## Batch 4

openproject, paperless, authentik, appflowy, plane, outline, karakeep, rocketchat, zulip, airflow, temporal, dagster, penpot, coolify, supabase, observability

**Status:** mixed — see breakdown below. `outline` also appears here (OIDC fix landed while working through this batch) as well as in Batch 3's fix notes above.

- ✅ **Running now:** `authentik`, `observability` — confirmed good. `observability` also got: a new `Stack Overview` Grafana dashboard (total/host memory, total CPU, per-container breakdown — answers "how much memory is the whole stack using" in one place), Grafana/Loki SMTP wired to Mailpit, and a Loki `reject_old_samples`/`ingester.max_chunk_age` fix so ordinary `up`/`down` restarts stop dropping buffered log lines. Building the dashboard surfaced a real Grafana 13 gotcha: pinning a datasource's `uid` in `datasources.yml` crash-loops an *already-provisioned* datasource (`Datasource provisioning error: data source not found`) — confirmed live, fixed by wiping `service_data/data/observability/grafana/` and letting it reprovision fresh (no data loss, everything here is file-provisioned) — documented in `docs/services/observability.md` as a required step for any existing install picking up this change.
- ✅ **Tested and confirmed good, currently offline** (stopped after testing, not broken): `paperless`, `appflowy`, `outline`, `rocketchat` (image bump to `8.7.0` + Mailpit SMTP wiring, brought up and back down clean), `supabase` (Mailpit SMTP wiring fixed in `.env.example`, Studio dashboard Basic Auth credentials confirmed set; brought down after use — not yet browser-verified end to end), `airflow`, `temporal`, `dagster` (self-seeding Docker image fix confirmed — auto-copies `worker.py`/`definitions.py`/example DAGs into the bind-mounted data dir on first empty start — see `docs/services/temporal/temporal.md`, `docs/services/dagster/dagster.md`, `docs/services/airflow/airflow.md`), `penpot`, `openproject` (image bump to `17.7.2` + Mailpit SMTP wiring; admin account reseeded from a clean `openproject-pgdata` volume with real name/email/random password via `OPENPROJECT_SEED_ADMIN_USER_*`, forced password-change confirmed working on first login), `karakeep` (Bucket C — real accounts, no admin/role tiering; `karakeep-chrome`'s image was failing to pull — `gcr.io/zenika-hub/alpine-chrome:124` started requiring GCP billing, an upstream GCR change — switched to `ghcr.io/karakeep-app/karakeep-chrome:release`, Karakeep's own maintained image; also bumped `meilisearch` to `v1.53.1` and wired Mailpit SMTP), `plane` (all 8 images bumped `v1.4.0 → v1.4.1`, brought up and back down clean), `zulip` (Mailpit SMTP already hardcoded in `compose.yml`; `.env.example` comment corrected after review caught it adding four `SETTING_EMAIL_*` lines that `env_file` can't actually override since `compose.yml`'s explicit `environment:` block always wins — removed rather than left as misleading dead config), `coolify` — by far the deepest dig of this batch, six distinct issues found and fixed, all documented in `docs/services/coolify.md`:
  1. Switched off `:edge` onto the real pinned tag `4.3.9` — stable semver tags existed on Docker Hub the whole time; the earlier "no stable release" conclusion came from checking Docker Hub's recency-sorted tag list instead of searching by tag name. Also bumped `postgres` (`18.4-alpine → 18.6-alpine`) and `coolify-realtime` (`1.0.16 → 1.0.17`), and documented "never use Coolify's in-app Upgrade button" — it forks Coolify onto its own CDN-downloaded compose files, bypassing this repo's tracked-version model entirely.
  2. `coolify-proxy` (Coolify's own Traefik, separate from `nginx-plain`) stuck on "starting" forever — wanted host port `8080`, already owned by `landing`; fixed by dropping the optional Traefik dashboard.
  3. Sentinel permanently "out of sync" — hardcoded push URL assumed Coolify's own standard install (host port `8000`); this stack publishes it on `8132` instead. `services/coolify/fix-proxy-sentinel.sh` reapplies both this and #2 after any fresh install, since both live in Coolify's database, not `compose.yml`.
  4. **The big one:** every `service_data/`-mounted volume in `compose.yml` pointed at `/data/coolify/...` — a path the image doesn't use at all — instead of the real `/var/www/html/storage/app/...`, meaning every SSH key/deployed-app config/database/backup/service was silently ephemeral, wiped on every container recreation, for as long as this compose file existed. Fixed all six mounts; `ssh` specifically moved to a named `coolify-ssh-keys` volume rather than a `service_data/` bind mount, since `service_data/` sits on an NTFS/`fuseblk` drive that can't store real Unix permissions at all (`chmod`/`chown` against it silently no-op forever), and OpenSSH's private-key mode check needs an actual `0600`.
  5. Terminal feature ("websocket connection lost, reconnecting" → later, real SSH errors once the WS itself worked): needed its own `nginx-plain` route (separate port-6002 process, not the `6001` Soketi one already fixed for live deploy logs), an `extra_hosts` entry on `coolify-realtime` (only `coolify` itself had it), and — the actual root cause once those two were fixed — a fresh `coolify-ssh-keys` volume starting out owned by `root:root`, which Coolify's own image doesn't self-heal on boot the way postgres/redis images do. `services/coolify/init-ssh-volume.sh` fixes this once, before the very first `up coolify` on any fresh install.
  6. Verified the complete fresh-install flow end to end for real, using Coolify's own onboarding wizard (confirmed it's the same `generateSSHKey()`/`PrivateKey::createAndStore()` code path either way) — full checklist now in `docs/services/coolify.md`'s Setup section. Also added `ROOT_USER_*` admin-seeding env vars, a `stop-self-managed.sh` script for `coolify-proxy`/`coolify-sentinel` (not in `compose.yml`, so `down coolify` never stops them), and confirmed the standard `backup`/`restore` flow already covers Coolify correctly for machine migration with no extra steps needed.
- ⬜ **Not yet started at all:** none — every Batch 4 service has been attempted at least once now.
- ⚠️ **`gitlab` — needs a fix before next start, not just a re-up.** Was running with an uncommitted image bump (`19.2.1-ce.0 → 19.2.4-ce.0`) plus new Mailpit SMTP config (still uncommitted in `services/gitlab/compose.yml`). A `gitlab-ctl reconfigure` at 15:02 restarted its internal services under the container's `memory: 6G` cap; ~18 minutes later the kernel started OOM-killing GitLab's `ruby` workers (Puma/Sidekiq) inside that cgroup, and it never stopped — **1,579 kills over 5 hours**, GitLab endlessly respawning workers that got killed again immediately. The host itself hung (black screen) and needed a hard power-off — journald's log for that boot just stops mid-crash-dump, no clean shutdown ever recorded. Confirmed healthy again after reboot, then intentionally stopped. Root cause (6G is too tight for GitLab CE, especially right after an upgrade) is **not yet fixed** — raise the memory limit in `compose.yml` before starting it again.

## Also confirmed good (outside the batch numbering)

- `plausible` — nginx-plain was missing WebSocket upgrade headers on its proxy block, which silently hung the LiveView-based "Create my account" flow (fixed, `docs/services/plausible.md`/`services/nginx-plain/templates/default.conf.template`). Tracking sites added for `www.${DOMAIN}` and `docs.${DOMAIN}`.
- `mailpit` — this stack's SMTP test-catcher, used by nearly every other service's Mailpit-wiring fix above.

Both `plausible` and `mailpit` were moved from `SERVICES_EXTRA` into `SERVICES_MIN` (always-on infra tier) once confirmed good — see `CLAUDE.md`'s tier list. `stirling-pdf` (full) was also moved out of `SERVICES_MANUAL` into `SERVICES_EXTRA` (image bump to `2.14.3` picked up, confirmed working) — only `gitlab` remains in `SERVICES_MANUAL` now.
