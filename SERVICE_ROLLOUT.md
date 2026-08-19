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

**Status:** ✅ all running.

## Batch 2

mailpit, adguard-home, open-webui, mealie, syncthing, miniflux, invoiceshelf, vikunja, nocodb, atuin

**Status:** ✅ all running. Notable fixes applied along the way:

- `adguard-home` — port 53 conflicted with `systemd-resolved`; bound to LAN IP via `DNS_BIND_IP` instead of `0.0.0.0`.
- `invoiceshelf` — required pre-created `storage/` subdirectories (documented gotcha); later hit `AUTORUN_LARAVEL_MIGRATION` racing the install wizard, fixed permanently in `.env`.
- `stirling-pdf` (full, manual) — enabled login (`SECURITY_ENABLELOGIN`); `stirling-pdf-lite` can't support login at all (ultra-lite image has no security module).
- `atuin` — client `sync_address` config gotcha, documented in `docs/services/atuin.md`.

## Batch 3 (in progress)

ollama, crowdsec, bookstack, mattermost, n8n, wallabag, orangehrm, listmonk, documenso, calcom

**Status:** 🔄 starting — running in background.

## Remaining not yet started

openproject, paperless, authentik, appflowy, plane, outline, karakeep, rocketchat, zulip, airflow, temporal, dagster, penpot, coolify, supabase, observability

(`gitlab` and `stirling-pdf` full-manual excluded/handled separately — `gitlab` is `SERVICES_MANUAL`, redundant with `forgejo`.)
