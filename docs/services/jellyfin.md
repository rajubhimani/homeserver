# Jellyfin

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Stream movies, TV shows, and music from your server.
**Port:** `8096` (host) → `8096` (container) | **Data:** `service_data/data/jellyfin/` | **Requires:** — | **Memory:** no hard limit set; measured idle ~161MB — but **RAM is not the real constraint here**. Jellyfin's own docs recommend 8GB and emphasize CPU/GPU, not RAM: without hardware acceleration, CPU-only transcoding of HEVC/AV1/VP9 or HDR tone-mapping is "very performance demanding" (jellyfin.org/docs/general/administration/hardware-selection/) — idle numbers say nothing about what happens during actual transcoded playback

## Setup

```bash
cp jellyfin/.env.example jellyfin/.env
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

## Scan speed / CPU utilization tuning

**Symptom:** library scans sit at <1% CPU on an idle, multi-core host and take a long time, even though cores are sitting unused. This is a widely-reported Jellyfin pattern (see jellyfin/jellyfin discussion #7249) — most of a scan's per-item work is waiting on TheMovieDB's network response, not compute, and Jellyfin's own auto-scaling for scan concurrency (`0` = auto in `system.xml`) has multiple open issues about under-delivering in practice (jellyfin/jellyfin#12203, #13531).

**Fix (only safe if media is on local/direct-attached storage, not a network share — high concurrency is hard on SMB/NFS):** `uv run jellyfin/apply-tuning.py` (sets `LibraryScanFanoutConcurrency`/`LibraryMetadataRefreshConcurrency` to the host's CPU core count instead of the `0`/auto default that multiple GitHub issues report under-delivering — override via `JELLYFIN_SCAN_CONCURRENCY` in `.env`; trickplay threads auto-derive to half that value). Raising scan concurrency is only safe *because* `LockingBehavior` is already set to `Optimistic` (above) by the same script; doing this on the default `NoLock` mode would likely reintroduce that bug, since higher concurrency means more concurrent DB writes.

**Honest result, not just "it worked":** this raised peak CPU during a scan (0.8% → 80.95% sampled via `docker stats`) and produced zero new `database is locked` errors, but did **not** resolve the underlying scan duration — a scan of this library (1,200+ movies alone, before TV) still took a long time. Root cause turned out to be more fundamental: most per-item work is a sequential remote TheMovieDB lookup, which local concurrency/CPU tuning can't speed up (TMDb's own response time is the ceiling, not local compute) — see the `ImageExtractionTimeoutMs` entry below for a real side effect this change introduced. **Bottom line:** worth doing since it's harmless and does use idle CPU productively, but don't expect it alone to fix a slow first scan of a large library — a first full scan of ~1,200+ items doing individual remote metadata lookups is going to take a while regardless; subsequent incremental scans (only new/changed files) should be much faster.

## Troubleshooting: `Error in Embedded Image Extractor` / `ffmpeg image extraction timed out ... after 10000ms`

**Symptom:** repeated `MediaBrowser.Common.FfmpegException: ffmpeg image extraction timed out for file:"..." after 10000ms` during a scan, often clustered on the same release/show — `ffmpeg` fails to pull an embedded preview thumbnail from a video file within Jellyfin's timeout and the operation gets cancelled (`TaskCanceledException`).

**Root cause:** `ImageExtractionTimeoutMs` in `system.xml` defaults to a ~10-second ceiling (`0` = default). This is tight for CPU-decoded HEVC/10-bit content (no hardware acceleration is configured for this deployment — see the `**Memory:**` note at the top of this doc), and gets worse under concurrent load: raising `LibraryScanFanoutConcurrency`/`LibraryMetadataRefreshConcurrency` (above) means multiple `ffmpeg` processes now run at once during a scan, and a live transcode/playback session running at the same time adds even more CPU contention on top of that — any of these alone can push a single extraction past the 10s ceiling.

**Fix:** `uv run jellyfin/apply-tuning.py` (sets `ImageExtractionTimeoutMs` to `30000`, up from the ~10s default — override via `JELLYFIN_IMAGE_EXTRACTION_TIMEOUT_MS` in `.env`). Community reports (jellyfin.org forum, jellyfin/jellyfin#8440, #13116) confirm 30s as a commonly-needed value for HEVC/10-bit content under load; not yet confirmed long-term in this deployment, but the specific errors stopped appearing immediately after applying it.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
