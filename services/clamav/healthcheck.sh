#!/bin/sh
set -eu

# 1. clamd itself must respond -- same check the image's own clamdcheck.sh
# does (PING/PONG over the clamd TCP protocol).
if [ "$(echo "PING" | nc localhost 3310)" != "PONG" ]; then
    echo "ERROR: clamd not responding"
    exit 1
fi

# 2. Signature database must have updated recently. A dead/misconfigured
# freshclam doesn't crash clamd or the container -- it just keeps scanning
# with whatever signatures it already has, silently, forever. Catching that
# here is the whole point: without this, the container reports "healthy"
# indefinitely even with months-stale signatures, since clamd's own PING
# response has nothing to do with freshclam's update status.
#
# "daily" is the database ClamAV publishes updates to most often (the name
# says as much); freshclam checks once a day by default (FRESHCLAM_CHECKS
# in services/clamav/.env), so requiring an update within the last
# CLAMAV_MAX_SIGNATURE_AGE_DAYS (default 3) means at least two consecutive
# missed checks before this fires -- a real problem, not a one-off blip or
# a day ClamAV simply didn't publish a new daily build.
#
# Checks BOTH daily.cvd and daily.cld: freshclam downloads the initial full
# database as daily.cvd, but once it starts applying incremental patches on
# top (its normal steady-state behavior, confirmed live -- this switched
# within the first update cycle after this healthcheck was added) it
# rewrites the result as daily.cld instead and daily.cvd stops being
# touched at all. Checking only .cvd would permanently report stale/missing
# the moment freshclam does its completely normal thing.
MAX_AGE_DAYS="${CLAMAV_MAX_SIGNATURE_AGE_DAYS:-3}"
if ! find /var/lib/clamav/daily.cvd /var/lib/clamav/daily.cld -mtime "-${MAX_AGE_DAYS}" 2>/dev/null | grep -q .; then
    echo "ERROR: daily signature database (.cvd/.cld) is older than ${MAX_AGE_DAYS} days -- freshclam may be failing (check: docker logs clamav | grep -i freshclam)"
    exit 1
fi

echo "clamd healthy, signatures updated within ${MAX_AGE_DAYS} days"
exit 0
