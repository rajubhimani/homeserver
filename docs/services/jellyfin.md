# Jellyfin

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Stream movies, TV shows, and music from your server.
**Port:** `8096` (host) → `8096` (container) | **Data:** `service_data/data/jellyfin/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~65MB — but **RAM is not the real constraint here**. Jellyfin's own docs recommend 8GB and emphasize CPU/GPU, not RAM: without hardware acceleration, CPU-only transcoding of HEVC/AV1/VP9 or HDR tone-mapping is "very performance demanding" (jellyfin.org/docs/general/administration/hardware-selection/) — idle numbers say nothing about what happens during actual transcoded playback

## Setup

```bash
cp services/jellyfin/.env.example services/jellyfin/.env
# set MEDIA_ROOT to your media drive path, and the JELLYFIN_* tuning vars below if you want non-default values
uv run homeserver.py dev up jellyfin
```

## First login

Open `http://<ip>:8096` — the setup wizard creates the admin account and lets you add library paths.

## Apply performance/reliability tuning (fresh install or any time)

`database.xml`/`system.xml` don't exist until the first-run setup wizard above has completed — run this **after** that, not instead of it:

```bash
uv run jellyfin/apply-tuning.py
```

Stops Jellyfin, applies the five settings below (each documented with its own symptom/root-cause under Troubleshooting), restarts it in whatever mode (dev/prod) it was already running in. Idempotent — safe to re-run any time, e.g. after tweaking a `JELLYFIN_*` value in `.env`. All five have sensible defaults baked into the script if left unset in `.env`:

| `.env` var | Default | Controls |
| --- | --- | --- |
| `JELLYFIN_SCAN_CONCURRENCY` | host CPU core count | `LibraryScanFanoutConcurrency` + `LibraryMetadataRefreshConcurrency` (trickplay threads = half this, min 1) |
| `JELLYFIN_LOCKING_BEHAVIOR` | `Optimistic` | `database.xml` → `LockingBehavior` |
| `JELLYFIN_IMAGE_EXTRACTION_TIMEOUT_MS` | `30000` | `system.xml` → `ImageExtractionTimeoutMs` |
| `JELLYFIN_TRICKPLAY_PROCESS_PRIORITY` | `Normal` | `system.xml` → `TrickplayOptions/ProcessPriority` |

Only raise `JELLYFIN_SCAN_CONCURRENCY` above 1-2 if `MEDIA_ROOT` is local/direct-attached storage — high concurrency is hard on network shares (SMB/NFS).

## Troubleshooting: `SQLite Error 5: 'database is locked'` during large library scans

**Symptom:** `Microsoft.Data.Sqlite.SqliteException: SQLite Error 5: 'database is locked'`, sometimes with a DB command timing out at the full 30s `CommandTimeout`, repeating throughout a large scan.

**Root cause:** confirmed known bug in Jellyfin 10.11.x itself (not specific to this deployment) — see [jellyfin.org/posts/SQLite-locking](https://jellyfin.org/posts/SQLite-locking/) and multiple open GitHub issues (e.g. jellyfin/jellyfin#15057, #13695, #15166). SQLite gets overwhelmed by concurrent write load during a full scan of a large library. The default locking mode (`NoLock`) does not fully avoid this for everyone even on 10.11.x.

**Fix:** `uv run jellyfin/apply-tuning.py` (sets `database.xml` → `LockingBehavior` to `Optimistic`, or override via `JELLYFIN_LOCKING_BEHAVIOR` in `.env` — see **Apply performance/reliability tuning** above). `Optimistic` retries writes automatically on lock conflicts instead of failing outright — confirmed this eliminated all `database is locked` errors in this deployment during an active large-library scan. If `Optimistic` isn't enough, Jellyfin's own docs describe a `Pessimistic` mode (serializes all writes, single-writer exclusivity) as the next step — significant performance cost, only worth trying if `Optimistic` doesn't hold; set `JELLYFIN_LOCKING_BEHAVIOR=Pessimistic` and re-run the script.

## Troubleshooting: streaming/SyncPlay hangs for ~1-2 minutes (not a scan)

**Symptom:** playback appears to freeze (pause/seek/stop feels unresponsive) for roughly a minute or two during normal viewing, no scan running. Logs show `Jellyfin.Database.Implementations.Locking.OptimisticLockBehavior: Operation failed retry N` (N incrementing every ~30s) bridging the gap between two session-state log lines (e.g. two `Playback stopped reported by app ...` lines ~2 minutes apart) — the request being retried is a session/progress write, not a scan write.

**Root cause:** same underlying SQLite contention as the scan issue above, triggered instead by a burst of concurrent write-heavy activity outside of scans — e.g. a SyncPlay group with 2+ users pausing/seeking together, concurrent transcode sessions, and subtitle-extraction ffmpeg jobs all landing on the DB at once. `Optimistic` mode (the fix above) retries these writes with a fixed ~30s backoff instead of failing, so the request eventually succeeds, but the client is left waiting the whole time — that wait is what reads as a hang.

**Tried and reverted: `JELLYFIN_LOCKING_BEHAVIOR=Pessimistic`.** This is the next escalation Jellyfin's own docs suggest, and it was tested live in this deployment. **Result: worse, not better.** Under the same kind of rapid-seek/concurrent-transcode load, `Pessimistic`'s single-writer serialization caused an outright failed request — `Jellyfin.Api.Middleware.ExceptionMiddleware: Error processing request: Unexpected end of request content. URL POST /Sessions/Playing/Progress` — instead of `Optimistic`'s slow-but-eventually-successful retry. The client gave up waiting on the serialized write queue before it was serviced. **Bottom line: stick with `Optimistic`.** A `Pessimistic` write queue is worse for this deployment's actual load pattern (multiple concurrent playback/transcode sessions) than occasional multi-retry stalls are — don't re-try `Pessimistic` for this symptom without a materially different load pattern to justify re-testing.

## Scan speed / CPU utilization tuning

**Symptom:** library scans sit at <1% CPU on an idle, multi-core host and take a long time, even though cores are sitting unused. This is a widely-reported Jellyfin pattern (see jellyfin/jellyfin discussion #7249) — most of a scan's per-item work is waiting on TheMovieDB's network response, not compute, and Jellyfin's own auto-scaling for scan concurrency (`0` = auto in `system.xml`) has multiple open issues about under-delivering in practice (jellyfin/jellyfin#12203, #13531).

**Fix (only safe if media is on local/direct-attached storage, not a network share — high concurrency is hard on SMB/NFS):** `uv run jellyfin/apply-tuning.py` (sets `LibraryScanFanoutConcurrency`/`LibraryMetadataRefreshConcurrency` to the host's CPU core count instead of the `0`/auto default that multiple GitHub issues report under-delivering — override via `JELLYFIN_SCAN_CONCURRENCY` in `.env`; trickplay threads auto-derive to half that value). Raising scan concurrency is only safe *because* `LockingBehavior` is already set to `Optimistic` (above) by the same script; doing this on the default `NoLock` mode would likely reintroduce that bug, since higher concurrency means more concurrent DB writes.

**Honest result, not just "it worked":** this raised peak CPU during a scan (0.8% → 80.95% sampled via `docker stats`) and produced zero new `database is locked` errors, but did **not** resolve the underlying scan duration — a scan of this library (1,200+ movies alone, before TV) still took a long time. Root cause turned out to be more fundamental: most per-item work is a sequential remote TheMovieDB lookup, which local concurrency/CPU tuning can't speed up (TMDb's own response time is the ceiling, not local compute) — see the `ImageExtractionTimeoutMs` entry below for a real side effect this change introduced. **Bottom line:** worth doing since it's harmless and does use idle CPU productively, but don't expect it alone to fix a slow first scan of a large library — a first full scan of ~1,200+ items doing individual remote metadata lookups is going to take a while regardless; subsequent incremental scans (only new/changed files) should be much faster.

## Troubleshooting: `Error in Embedded Image Extractor` / `ffmpeg image extraction timed out ... after 10000ms`

**Symptom:** repeated `MediaBrowser.Common.FfmpegException: ffmpeg image extraction timed out for file:"..." after 10000ms` during a scan, often clustered on the same release/show — `ffmpeg` fails to pull an embedded preview thumbnail from a video file within Jellyfin's timeout and the operation gets cancelled (`TaskCanceledException`).

**Root cause:** `ImageExtractionTimeoutMs` in `system.xml` defaults to a ~10-second ceiling (`0` = default). This is tight for CPU-decoded HEVC/10-bit content (no hardware acceleration is configured for this deployment — see the `**Memory:**` note at the top of this doc), and gets worse under concurrent load: raising `LibraryScanFanoutConcurrency`/`LibraryMetadataRefreshConcurrency` (above) means multiple `ffmpeg` processes now run at once during a scan, and a live transcode/playback session running at the same time adds even more CPU contention on top of that — any of these alone can push a single extraction past the 10s ceiling.

**Fix:** `uv run jellyfin/apply-tuning.py` (sets `ImageExtractionTimeoutMs` to `30000`, up from the ~10s default — override via `JELLYFIN_IMAGE_EXTRACTION_TIMEOUT_MS` in `.env`). Community reports (jellyfin.org forum, jellyfin/jellyfin#8440, #13116) confirm 30s as a commonly-needed value for HEVC/10-bit content under load; not yet confirmed long-term in this deployment, but the specific errors stopped appearing immediately after applying it.

## Troubleshooting: playback stutters/hangs between frames in Firefox but not Chrome (HEVC content)

**Symptom:** video judders or briefly hangs every ~10-60s during playback of HEVC/H.265 (x265) content, specifically in Firefox on Windows — the same title plays smoothly in Chrome/Edge. Server-side metrics look fine during the stutter (CPU low, disk idle, no ffmpeg errors/retries in `docker logs <jellyfin container>`).

**Root cause:** Chrome has no HEVC support at all, so Jellyfin transcodes the video to H.264 for it — H.264 has universal hardware decode, so it's smooth. Firefox on Windows, however, can claim HEVC support via the OS's Media Foundation decoder, so Jellyfin sees that and sends the video with `-codec:v:0 copy` (direct stream, no transcode — confirmed via `docker logs`). Firefox's actual use of that OS decoder path is inconsistent and often falls back to software HEVC decode, which struggles with 10-bit HEVC at higher resolutions — the judder is client-side decode, not a server/network issue.

**Fix:** disable Firefox's HEVC capability advertisement so Jellyfin transcodes to H.264 for it too, same as Chrome. The exact pref name has changed across Firefox versions, so set both:

1. `about:config` → search `media.hevc.enabled` → set to `false`/`0`
2. `about:config` → search `media.wmf.hevc.enabled` → set to `0`
3. Fully quit Firefox (not just close the tab/window — HEVC capability is cached per-session) and relaunch.
4. Reload the Jellyfin page fresh so it re-runs its `canPlayType()` capability probe against the server.

Confirm the fix took by checking the ffmpeg command in `docker logs` — it should now show `-codec:v:0 libx264` (or similar) instead of `-codec:v:0 copy` for HEVC source content. Confirmed working in this deployment (`media.wmf.hevc.enabled` was the effective pref).

If still direct-streaming after both prefs are set, Windows' own "HEVC Video Extensions" (Microsoft Store codec pack), if installed, can make Firefox report HEVC support independent of these prefs — uninstalling/disabling that extension is the next step, or just manually cap the stream quality/bitrate in the Jellyfin Web player's playback settings per-session as a workaround.

## Fixed: `MEDIA_ROOT` was nested inside `DATA_ROOT`, so every backup archived the whole media library

**Symptom:** `uv run homeserver.py dev backup jellyfin` (and any auto-snapshot on `down`) took an extremely long time and produced a huge `service_data.tar.gz`, even though `config/` + `cache/` together are only ~3.5GB.

**Root cause:** this deployment's `.env` had `MEDIA_ROOT=../service_data/data/jellyfin/media` — nested *inside* `DATA_ROOT` (`service_data/data/jellyfin/`) instead of pointing at an external path like `.env.example`'s documented default (`/mnt/seagate/media`). `backup_service()` in `homeserver.py` tars the entire `DATA_ROOT` directory on every backup/auto-snapshot, so the whole movie/TV library was being re-archived every time alongside the actual config/db.

**Fix:** moved media out to `service_data/media/jellyfin/` — a sibling of `service_data/data/`, structurally outside anything `backup_service()` sweeps — and updated `MEDIA_ROOT` accordingly. The container's mount target (`/media`) didn't change, only the host-side source path, so no library rescan was needed; Jellyfin's internal paths are relative to the container mount point, not the host path. Confirmed fix: a backup taken after the move completed immediately with no media in the archive. This is now a documented convention (see the `homeserver-add-service` skill, step 2) for any service with a second, large secondary data root — `immich`'s `UPLOAD_LOCATION` had the identical bug, fixed the same way (see `docs/services/immich.md`); `dockge`'s `DOCKGE_STACKS_DIR` had the same pattern too (fixed, though it had no live deployment to migrate).

## Fixed: `config/metadata` cache was also nested inside `DATA_ROOT`

**Symptom:** even after the `MEDIA_ROOT` fix above, `down all`/backup snapshots were still slow — `service_data/data/jellyfin/config/metadata` (downloaded poster/fanart/NFO cache) had grown to 1.2GB and was still being fully re-archived on every backup.

**Root cause:** unlike `MEDIA_ROOT`, this directory isn't a top-level `.env` var — Jellyfin populates `config/metadata/` on its own during library scans (same class of issue as `open-webui`'s embedding-model cache, see the `homeserver-add-service` skill step 2's retrofit note). It was never flagged because it's a subdirectory of `config/`, not a separate declared root.

**Fix:** added a new `METADATA_ROOT` env var (`../service_data/cache/jellyfin/metadata`), mounted over `/config/metadata` as a second bind mount layered on top of the `/config` mount in `compose.yml`. Moved the existing 1.2GB directory to the new path before restarting — no rescan needed, same reasoning as the `MEDIA_ROOT` fix (container-side path unchanged). Fully regenerable if ever lost: Jellyfin re-downloads metadata from providers (TMDB etc.) on the next library scan.

## Decommissioned: Postgres-backend test instance

A separate, manual-only `jellyfin-pgsql-test` instance ran on a community Postgres fork ([JPVenson/Jellyfin.Pgsql](https://github.com/JPVenson/Jellyfin.Pgsql)) to test whether Postgres avoids the `OptimisticLockBehavior` write-stall documented above. It confirmed a real bug in that fork (crash-loops on restart once it has data — no `DROP`/`IF NOT EXISTS` guards in its backup/restore logic) and was never made production-safe, per the fork maintainer's own "HIGHLY experimental" warning.

Before teardown, the watch history/favorites that had accumulated on the test instance (~4,000 `UserData` rows, plus its downloaded poster/fanart cache) were merged into this real instance's SQLite DB and metadata cache — matching rows by item path/`ItemId`, since Jellyfin generates item GUIDs deterministically from the file path, so the same media file gets the same `Id` in independently-scanned libraries. Two accounts (`TV`, `neerajbadal`) that only existed on the test instance were recreated here via the Jellyfin API to receive their migrated data. One gotcha hit during the merge: CSV-importing Postgres `NULL`s produced empty strings (`''`) instead of SQLite `NULL`s in the `LastPlayedDate`/`RetentionDate` columns, which crashed item-detail API calls with a `DateTime` parse error — fixed with `UPDATE UserData SET LastPlayedDate = NULL WHERE LastPlayedDate = ''` (and the same for `RetentionDate`).

The `jellyfin-pgsql-test` container, its Postgres volume, `service_data/data/jellyfin-pgsql-test/`, `service_data/cache/jellyfin-pgsql-test/`, and the `jellyfin-pgsql-test/` compose directory have all been removed.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
