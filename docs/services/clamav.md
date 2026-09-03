# ClamAV

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Antivirus scanning daemon backing [Nextcloud](nextcloud.md)'s `files_antivirus` app. No UI of its own — a pure backend `clamd` daemon reached only over the internal Docker network, never through the reverse proxy.
**Port:** `8152` (host, dev-only debugging) → `3310` (container, `clamd`'s TCP protocol) — no public route, nothing here should ever be reachable from outside this host. | **Data:** `service_data/cache/clamav/db/` — the virus-signature database only, fully regenerable via `freshclam` re-download, so it lives under `cache/` rather than `data/` (see the `homeserver-add-service` skill's data-bucket rules) — nothing here needs backing up. | **Requires:** nothing | **Memory:** measured idle with signatures loaded: **~950MB** — this is the heaviest service added to this stack so far by a wide margin, driven entirely by ClamAV's own signature database living in RAM (upstream's own docs: "Preferred: 4 GiB", loading signatures alone needs "upwards of 1.2 GiB"). `compose.yml` caps it at 3GB via `deploy.resources.limits`.
**Pinned version:** `clamav/clamav:1.5.4_base` — the `_base` variant ships without a bundled signature database (downloaded fresh via `freshclam` into the persistent `CACHE_ROOT` volume instead), which upstream's own docs recommend specifically to avoid re-pulling the full database as part of every image pull once it's already persisted.

## Setup

```bash
cp services/clamav/.env.example services/clamav/.env
uv run homeserver.py dev up clamav
```

First start downloads the full signature database via `freshclam` (a few hundred MB) — `CLAMD_STARTUP_TIMEOUT=1800` (30 minutes, the image's own documented default) gives it room to finish before the container's healthcheck gives up. Confirmed on this deployment: actual first-run download took well under a minute, not anywhere near the worst-case 30-minute allowance — that ceiling is there for slow/constrained connections, not the expected case.

## Wiring up Nextcloud's `files_antivirus`

```bash
docker exec -u www-data nextcloud php occ app:enable files_antivirus
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_mode --value="daemon"
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_host --value="clamav"
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_port --value="3310"
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_infected_action --value="only_log"
docker exec -u www-data nextcloud php occ config:app:set files_antivirus av_stream_max_length --value="104857600"
```

**`av_infected_action=only_log`, not `delete`, is a deliberate default here** — logs a detection instead of silently removing the file. Given a real infected upload is rare on a small family instance and false positives do happen with AV engines generally, log-and-review is the safer default than automatic deletion; switch to `delete` explicitly if that tradeoff isn't wanted.

**`av_stream_max_length=104857600` (100MB)** caps how much of a file gets streamed to `clamd` for scanning — must not exceed PHP's own `memory_limit` (`512M` in this stack's `nextcloud/.env.example`), since the stream is buffered in PHP memory during the scan.

## Verifying it's actually working — don't just trust "container healthy"

A healthy `clamav` container only proves the daemon started, not that Nextcloud is actually using it. Confirmed working here via the app's own built-in self-test:

```bash
docker exec -u www-data nextcloud php occ files_antivirus:test
```

Expected output: `Scanning regular text: ✓` and `Scanning EICAR test file: ✓` (the standard, harmless [EICAR test string](https://en.wikipedia.org/wiki/EICAR_test_file) that every antivirus engine recognizes as a positive-detection test, not a real virus). A third check — `Scanning modified EICAR test file` — tests a slightly obfuscated variant and reported `❌ file not detected` on this deployment; that's a narrower heuristic-matching gap, not a connectivity/config problem, and doesn't indicate the daemon-mode integration itself is broken.

## Scanning is background/queued, not synchronous on upload

**This tripped up initial verification** — uploading a real EICAR test file via WebDAV produced no scan activity at all (no log entry, no connection to `clamd`), which looked like the integration was silently broken. It wasn't: `occ files_antivirus:status` showed a backlog of unscanned files (`390 unscanned files` at the time), confirming files_antivirus queues writes for a **background** scan pass rather than blocking the upload request itself. Trigger it manually:

```bash
docker exec -u www-data nextcloud php occ files_antivirus:background-scan
```

Runs automatically as part of Nextcloud's own background job system otherwise (`cron.php`, via `nextcloud-cron` — see `docs/services/nextcloud.md`'s "Architecture notes") — no scheduling changes needed here, uploads just aren't scanned the instant they land.

## Testing detection end-to-end

```bash
# Upload a real EICAR test file via WebDAV (harmless, universally-recognized AV test signature)
curl -u '<user>:<app-password>' -T /dev/stdin \
  "https://nextcloud.${DOMAIN}/remote.php/dav/files/<user>/eicar-test.txt" \
  <<< 'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'

# Then trigger a scan pass (or wait for the next background job run)
docker exec -u www-data nextcloud php occ files_antivirus:background-scan
```

With `av_infected_action=only_log`, an infected file stays in place but the detection is logged — check `nextcloud.log` (or the Nextcloud admin notifications) for an `files_antivirus` entry naming the file, not a blocked upload.

## Detecting a silently-failing signature update

**The real risk here isn't `clamd` crashing — it's `freshclam` failing quietly.** If the daily update check fails (network issue, DNS, upstream rate-limiting), nothing crashes: `clamd` keeps running and scanning fine with whatever signatures it already has. Confirmed directly from the image's own healthcheck script (`clamdcheck.sh`) before this was fixed: it only pings `clamd` on port 3310 and checks for a `PONG` — it says nothing about signature freshness. A container could sit at `healthy` in `docker ps` for months with stale signatures and nothing would ever say otherwise.

**Fixed via a custom healthcheck** (`healthcheck.sh`, bind-mounted over the image's default, `compose.yml`) that does both checks:
1. The original `clamd` ping.
2. `find`s `/var/lib/clamav/daily.cvd` **and** `/var/lib/clamav/daily.cld` for an mtime within `CLAMAV_MAX_SIGNATURE_AGE_DAYS` (default `3`, `.env`). If neither exists or both are older than that, the healthcheck fails — `docker ps` shows `unhealthy`, giving something real to alert on instead of a silent gap.

**Checking both filenames matters — confirmed live, not assumed.** `freshclam` downloads the initial full database as `daily.cvd`, but its normal steady-state behavior is applying incremental patches on top and rewriting the result as `daily.cld` instead — `daily.cvd` stops being touched entirely once that happens. This switch was observed within the very first update cycle after this healthcheck was added; a version checking only `.cvd` would have started reporting permanently stale/missing the moment `freshclam` did its completely ordinary thing, which very nearly shipped that way before catching it via a real restart-and-check rather than trusting the logic on paper.

**3 days, not 1**, gives freshclam (which checks once daily via `FRESHCLAM_CHECKS`) room for a one-off blip without alerting — the check only fires after at least two consecutive missed days.

## Proactive alerting — `clamav-watchdog`

Still no landing-page card (this service has none, see "Purpose" above), but the healthcheck status no longer requires manually running `docker ps`/`docker inspect` to notice — `clamav-watchdog` (`compose.yml`, `watchdog.sh`, same pattern as `services/adguard-home/`'s watchdog) polls the Docker API every `WATCHDOG_CHECK_INTERVAL` seconds (default 300) for whether `clamav` is actually reporting `healthy`, and pushes a real push notification via [ntfy](ntfy.md) after `WATCHDOG_FAIL_THRESHOLD` consecutive misses (default 2 — at least 10 minutes of real unhealthiness, not a one-off blip), with a `WATCHDOG_ALERT_COOLDOWN` (default 6h) so it doesn't re-alert every single check interval while the problem persists.

Publishes to ntfy's `homeserver-alerts` topic over the internal Docker network (`NTFY_ALERT_URL=http://ntfy/homeserver-alerts` — no reason to round-trip through Cloudflare for a container-to-container call), authenticated with a dedicated access token (`NTFY_ALERT_TOKEN`, `ntfy token add --label=homeserver-alerts <user>` — never the real account password; see [ntfy.md](ntfy.md) for the current account). Verified working end-to-end with the actual production credentials, not just each piece in isolation: the watchdog's Docker-socket health query, and a real alert publish using the exact token/URL loaded inside the running `clamav-watchdog` container, both confirmed live before this shipped.

**This alert is silent until you actually subscribe to it** — see [ntfy.md](ntfy.md)'s `homeserver-alerts` section for the one-time phone/browser subscription step; nothing plays that step for you.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
